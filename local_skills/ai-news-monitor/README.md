# ai-news-monitor

A skill that sweeps the web for news on **agentic AI and the stack
underneath it** — agent frameworks and protocols, inference and serving,
hardware and silicon, model releases, evals, and the policy and security items
that constrain deployment — and produces a deduplicated, primary-source-verified
digest that only shows what is new since the last run.

This README is for humans deciding whether to use, trust, or modify the skill.
`SKILL.md` is the model-facing instruction set; the two say the same thing at
different altitudes.

It is deliberately harness-agnostic. `SKILL.md` is prose any capable agent can
follow, and the only capabilities it assumes are web search, fetching a page, and
running Python — no tool is named, and nothing depends on a particular runtime.
The stored state follows the XDG spec rather than living under any one client's
config directory.

---

## Quick start

Ask for it in plain language. The skill is written to trigger without being
named:

```
what's new in agentic AI this week
catch me up on AI, I've been offline since June
any news on inference or GPUs?
did anything happen with MCP lately?
give me a weekly AI briefing
```

First run has no history, so it defaults to a 7-day window. Every run after that
starts from where the last one stopped.

For a standing monitor, drive it with the `schedule` skill (cloud cron, good for
a daily or weekly digest) or `/loop` (good for watching something inside one
session).

---

## The one thing to understand first

The `scripts/` directory is executable code; everything else in this skill is
**instructions the model reads and follows**. That split determines what you can
rely on:

| Part | Enforced by | Guarantee |
|---|---|---|
| Deduplication, URL canonicalisation, run timestamps, mrkdwn conversion | Python | Deterministic |
| Beat selection, search strategy, primary-source verification, ranking, digest | The model, guided by `SKILL.md` | Discipline, not enforcement |

So: duplicates *will not* get through. "Verified against the primary source" is a
strong habit the skill instills, not a check it enforces. Judge the output
accordingly — and note the digest is required to declare its own gaps in a
**Coverage notes** section, which is your main signal for how much a given run
actually verified.

---

## What a run does

### 1. Scope

- **Window** — `ledger.py status` reports `last_run` (and `last_window`, the free-text note of what the previous run covered). If it exists, the window is
  from then until now; if it says `never`, the default is 7 days. An explicit ask
  ("this month", "since CES") wins. Today's date comes from `date -u +%F` rather
  than model memory, because the window is the one fact a digest cannot afford to
  get wrong. `ledger.py new` derives the same window by the same rule and filters
  on it in step 3, so the window is enforced rather than merely stated — see
  **The window gate** below.
- **Beats** — defaults to **all seven** in `references/beats.md`. Narrows only
  when the ask itself is narrow ("any vLLM news"). A quick check runs fewer
  queries per beat rather than dropping beats, since the point of a monitor is
  that the reader need not guess in advance where the important thing will come
  from.
- **Depth** — proportional to the ask. "Anything new with MCP?" is not supposed to
  become a twenty-source sweep.
- **Interests** — optional, per profile, and off by default. A standing line on
  what a reader works on ("runs vLLM on H200s, cares about long-context serving
  cost, not consumer AI"), stored in `state.json` and read at ranking time. It
  reweights; it never filters — a critical security disclosure still reaches a
  reader who only asked about inference, because the point of a monitor rather
  than a saved search is to hear what you did not know to ask about. An interest
  stated in the request wins over the standing note for that run. This is the
  reader's state, never the skill's: the skill stays generic so several people
  with different subfields can share one copy.
- **Destination** — settled before writing, because it decides format, budget and
  whether a file exists. Default is the conversation; a file when asked, when the
  run is unattended, or when something downstream consumes it, in the location
  given or the directory the run was invoked from. A platform-bound digest is
  produced in that platform's format and handed over — the skill never posts
  anything. Working files go to a per-run directory that `ledger.py start-run`
  empties and prints — the store path with `.run` appended, so it is derived from
  the store rather than invented, and any later step recomputes it instead of
  carrying it. Emptied when the run starts, because a run that fails never reaches
  a cleanup step and it is the failed run whose leftover `digest.md` the next one
  checks and delivers. Never a random directory, since each command is a fresh
  shell and a random name is unrecoverable the moment the command that made it
  returns; never the user's project; and never the skill's own directory — that
  one is shared by every run and replaced by the next sync, and both scripts
  refuse a path inside it.
- **Length** — no budget by default; write what the window warrants. A named
  destination can imply one: a Slack-bound digest budgets 3800 characters per
  part, since Slack recommends at most 4000 in a message's text. Use 2900 if the
  caller wraps parts in Block Kit section blocks, whose 3000 is a hard limit.
  When the ask carries its own budget ("under 2500 characters", "keep it brief"),
  it shapes the writing rather than trimming the result: bodies compress first,
  headlines demote to one-liners second, and if it still does not fit the digest
  **splits into parts rather than dropping anything**. A budget constrains the
  container, not what is worth telling the reader; the only items ever cut are
  those the ranking rejected on merit. Primary-source URLs, the caveats that
  decide whether to believe a number, and the Coverage notes never compress —
  links in particular are usually where a chat-sized budget actually goes, and
  stripping one destroys the reader's ability to check the claim.

### 2. Sweep

Several searches per beat, drawn from a per-beat query bank, with the current
month and year substituted in, issued in parallel. Two habits carry most of the
yield:

- **Search the vocabulary, not the topic.** `"AI news"` returns consumer stories.
  `"disaggregated prefill throughput benchmark"` returns the thing that matters.
- **Go direct where signal is dense.** For fast-moving projects, the GitHub
  releases page or changelog beats any search, and gets fetched directly.

Candidates are collected as `{url, title, source, date, beat}` *without* being
read yet — reading happens after deduplication, so no fetch is spent on a story
about to be discarded.

### 3. Deduplicate

Two passes; see [Deduplication](#deduplication-how-it-actually-works) below for
the mechanics.

### 4. Verify

Every item destined to be a headline gets its primary source opened, to confirm
the date and any number quoted. Search snippets are summaries, they go stale, and
they are where `2× faster` loses its `on H200 at batch size 64`.

Per-beat caveats are applied here: throughput claims need hardware, batch size
and precision; hardware announcements need an availability date; benchmark
results must state whether they are self-reported; a model "release" needs
weights, an API or a paper behind it, or it is labelled a preannouncement.

A source that cannot be reached — paywall, JS-only page, dead link — is declared
in the digest rather than reconstructed from the snippet.

### 5. Rank

By what changes a reader's decisions, not by how loud the coverage was.

**Leads:** something now buyable, installable or callable that was not before ·
a number that moves a real tradeoff (cost per token, throughput, context limit,
accuracy at a given precision) · a capability demonstrated with an eval, or an
eval showing a claimed capability fails · a constraint with a date on it
(deprecation, price change, rule taking effect) · a concrete failure (exploit
class, incident, failed reproduction).

**Cut or compressed to one line:** restated press releases and roadmap slides
with no ship date · funding rounds that change nobody's access to compute ·
opinion, predictions, listicles · leaderboard movement with no methodology.

Target is 3–6 headlines, with explicit permission to write fewer. A quiet week is
a real finding, and padding it is the fastest way for a recurring monitor to lose
its reader.

### 6. Write

`assets/digest-template.md` sets the shape: the period covered in the header, a
top line that reads on its own, headlines that carry the fact rather than the
topic ("TensorRT-LLM ships FP4 decode, 1.8× on B200" over "NVIDIA inference
update"), then **Also notable**, **Watching**, and **Coverage notes**.

**Every URL is one the run actually retrieved**, never reconstructed from a
guessed slug, and `scripts/check_links.py` verifies that mechanically before
delivery:

```bash
python3 scripts/check_links.py <run>/digest.md \
        --retrieved <run>/retrieved-urls.txt --json > <run>/link-check.json
```

`--retrieved` names the record the sweep builds as it goes, and any citation
absent from it is `UNSOURCED`. Reachability alone cannot catch a fabrication:
a slug guessed from a headline resolves on any site that builds URLs that way,
so it answers `OK` while citing a page nobody opened.

It reports verdicts rather than pass/fail, because many good sources refuse
automated requests — openai.com answers 403, CNN 451. `BROKEN` (malformed,
placeholder domain, unresolvable host, 404/410) fails the run; `BLOCKED` is a
prompt to confirm you opened the page yourself, not a defect. Stdlib only, and
`--offline` skips the network entirely.

It reads `[label](url)`, `<url>`, `<url|label>` and bare URLs — the last because
a digest citing its sources as `- **URL:** https://…` is the ordinary case. A
checker that recognised only the bracketed forms found no links in such a
digest, reported none, and exited zero, which read as a clean gate. Finding no
links is therefore a failure: a gate that inspected nothing has been skipped
rather than satisfied, and a digest citing nothing cannot support a published
item either way.

`--json` writes a **receipt** — the verdicts, whether provenance was checked at
all, and which files were read with their sha256 — and step 7's `add --verified`
will not record an item as published without one. That connection is the point.
A run once produced a complete seven-item digest in which every URL was
invented, with `broken`, `unreachable` and `404` all in its own log; the check
had already caught it and the items were recorded anyway, because reading a
verdict and acting on it are two different things. Detection was never what was
missing.

The receipt says what wrote it. `add` requires the header check_links stamps and
a verdict it recognises on every result, so a receipt written by hand is refused
by name rather than silently read as a verdict of "". That failure is not
hypothetical either: when the check above found nothing, a run wrote its own
receipt in a schema the script cannot emit and delivered on it. A receipt is the
output of a check; anything else is an opinion about the links wearing its
clothes.

The verdict travels as a file rather than as a second probe, so `add` stays a
local append: a fast write that reached the network would gain timeouts,
proxies and rate limits, and would be the skill's second implementation of a
check it already has.

What it cannot settle is whether a working link actually says what it was cited
for. That is what the retrieved-it-yourself rule is for.

**The digest is written to stand alone.** The reader may be someone it was
forwarded to, with no knowledge of this skill. So the internal machinery stays
internal: beats are never named, the sweep is never described, and no line
reports how many candidates were filtered or whether a ledger existed. Items are
tagged with plain topic labels — `Agents & protocols`, `Inference & serving`,
`Hardware`, `Models`, `Evaluation`, `Business & infrastructure`, `Policy &
security` — which map onto the beats without exposing them. Coverage notes
declare things that affect trust in the text (a figure taken as published, a
source that would not load), never scope of effort.

**Markdown is the output**, and in almost every run it is also what is
delivered. Slack renders `mrkdwn` rather than Markdown, so
`scripts/md_to_mrkdwn.py` exists — but the question it answers is not which
platform the digest is headed for, it is whether anything stands between the
digest and the wire:

```bash
uv run scripts/md_to_mrkdwn.py <run>/digest.md --divider -o <run>/digest.slack.txt
```

Convert only when producing the exact bytes something else posts verbatim. When
the digest is a reply, or a file someone opens, deliver Markdown: whatever
carries a reply into a chat destination renders it, so converting first means
rendering twice — and the second pass cannot undo the first, it can only act on
what the conversion got wrong. Converting also flattens anything the destination
renders specially, a pipe table most of all, and that is not reversible either.
Converting speculatively is a mistake in the other direction too: a destination
that does not speak mrkdwn shows it as literal punctuation. Both files are kept
when a conversion does happen — the Markdown is the artifact, the converted copy
serves one destination — and the converter needs `uv` and a package from the
network, which is one more thing to fail in a run nobody is watching.

The digest is written to `<run>/digest.md` (`digest-part-N.md` when split) and
checked there, whatever the destination — the link gate reads a file, so one
always exists. Output then goes wherever Step 1 settled: the conversation by
default, or a copy named `ai-digest-YYYY-MM-DD.md` (`-part-N.md` when split)
when a file was asked for.

### 7. Record

Everything reported goes into the ledger and the run is stamped. Skipping this
is the one failure that compounds — an unrecorded run means the next digest
re-reports everything.

`add` refuses to record an item as published unless it can establish where the
item came from, so the receipt from step 6's link check comes with it:

```bash
python3 scripts/ledger.py add -i <run>/reported.json --verified <run>/link-check.json --window 7d
```

`OK` and `BLOCKED` count as usable, matching the check's own exit code. `BROKEN`,
`UNSOURCED`, and a URL absent from the receipt do not — absent means the digest
that was checked never cited it, which is what happens when an item appears after
the check or the check ran against a draft.

`add` applies the window here too, the same one `new` applied in step 3 —
derived the same way, overridable with the same `--window-start` /
`--window-end`, and honouring the same three `window_exception` codes, which it
also stores. `new` filters its own output, but nothing made the published set a
subset of that output, so an item introduced after step 3 was never checked at
all. Record the whole run in one `add`: a second call reads back the stamp the
first wrote and derives a one-day window.

Unlike the window filter on `new`, both of these refuse rather than filter: they
exit non-zero and write nothing at all, neither the items nor the run stamp. By
this point the digest exists, so dropping an item quietly would leave it
published and unrecorded — the worse of the two states. Entries carrying
`duplicate_of` or `reason` were never shown to a reader and are exempt from both.

What a refusal guarantees is that nothing was written: no item recorded, the
clock unmoved, the profile still legible to the next run, and the call repeatable
after a fix with no cleanup. What it does not do is prevent delivery. Chaining
the steps — `add && deliver` — makes the shell enforce the order, and is worth
doing whenever delivery is a command. Where the digest is a reply there is no
`&&` and nothing mechanical between the refusal and the reader; only the order
of the steps holds, and only because the run follows it. A run has already
delivered a digest whose `add` had just refused every item in it, so the skill
states the property as a rule to follow rather than a guarantee it can make.

---

## Sources

There is no fixed feed list, and `references/sources.md` is deliberately **a map
for escalation, not a whitelist**. It ages; the field's most useful source in six
months may not be on it. Its job is to answer "does this claim have an
authoritative home I should be reading instead?"

**Primary — cite these, not coverage of them**
Lab release notes, model cards and pricing pages (Anthropic, OpenAI, Google
DeepMind, Meta, Mistral, Qwen, DeepSeek, Ai2, Cohere, xAI) · serving-project
GitHub releases (vLLM, SGLang, TensorRT-LLM, llama.cpp, Ollama, Ray Serve,
KServe, LMDeploy, TGI) · agent framework and protocol changelogs (MCP spec,
LangChain/LangGraph, LlamaIndex, OpenAI Agents SDK, Claude Agent SDK, AutoGen,
CrewAI, smolagents, Semantic Kernel) · hardware vendor newsrooms and developer
blogs, plus MLPerf for cross-vendor numbers · arXiv cs.LG/cs.CL/cs.AI/cs.DC,
Hugging Face papers, OpenReview · official regulator texts when a policy item
has a date attached.

**High-density secondary — attribute as commentary, not fact**
Practitioner systems blogs · semiconductor and supply-chain analysts · Hacker
News and r/LocalLLaMA for early signal on open-weight releases and real-world
failure reports · MLSys, NeurIPS, OSDI/SOSP · company engineering blogs
describing production agent deployments, which are rare and disproportionately
valuable.

**Handled with named care**
Self-reported leaderboard entries · code-free preprints with extraordinary
claims, reported as "claimed, unreplicated" or not at all · rumour accounts, only
if a named outlet has picked it up and labelled unconfirmed · paywalled analysis,
where nothing behind the wall is ever inferred · vendor benchmarks against
unnamed competitors, where the digest reports both the number and the fact that
the comparison is vendor-run.

---

## Deduplication: how it actually works

A monitor that repeats itself gets ignored, so this is the part with real code
behind it. Each candidate gets two independent fingerprints.

**1. URL canonicalisation** — reduce a URL to the document it identifies:

- force `https`, lowercase the host, strip `www.` and `:80`/`:443`
- drop tracking parameters by prefix (`utm_`, `mc_`, `pk_`, `hsa_`, `vero_`,
  `_hs`) and by exact name (`ref`, `fbclid`, `gclid`, `gbraid`, `igshid`, `spm`,
  `smid`, `share_id`, and about a dozen more)
- sort the surviving parameters; strip a trailing `/` and a trailing `/amp`

A newsletter link and a search hit for the same article now collapse to one key.

**2. Title fingerprinting** — catch syndication and near-verbatim rewrites:

- tokenise to `[a-z0-9]+`, drop a 62-word stoplist of headline filler
  (`announces`, `unveils`, `launches`, `debuts`, `reveals`, `new`, `why`, `how`…)
  and any token of 2 characters or fewer
- stem each token by suffix stripping (`ing` at ≥6 chars, `ed` ≥5, `es` ≥5,
  `s` ≥4), so `retires` / `retiring` / `retired` all become `retir`
- treat **Jaccard overlap ≥ 0.72** as the same story
- compare only against items from the **last 45 days**, since old headlines
  legitimately recur

Both run against the stored ledger *and* within the incoming batch.

**Be realistic about what this catches.** A smoke test against live search results
found the 0.72 threshold firing *zero* times — every suppression came from the
URL pass. Independent coverage of one event shares far less headline vocabulary
than intuition suggests:

```
"Kimi K3 open weights arrive July 27, the catch is 1.4TB"
"Kimi K3 Open Weights: 2.8T Params, Day-0 Hosting"              → 0.30
```

and the threshold cannot simply be lowered to compensate, because genuinely
distinct stories score *higher*:

```
"vLLM v1.1.0 adds FP4 decode kernels"
"SGLang v0.5 adds FP4 decode kernels"                           → 0.60
```

Title matching therefore reliably catches mirrors, syndication and near-verbatim
rewrites. It does not catch two outlets writing up the same event in their own
words.

**3. Hints — the script points instead of deciding.** Rather than lower the
threshold and risk merging real stories, anything scoring **≥ 0.22** but below
the drop threshold is kept and annotated:

```json
{"url": "...", "title": "AMD Delivers Breakthrough MLPerf Inference 6.0 Results",
 "_maybe_same_as": [{"title": "MLPerf Inference v6.0 results: AMD MI355X...",
                     "similarity": 0.36}]}
```

Up to two hints per item, ranked by similarity, drawn from both the ledger and
the current batch. Nothing is dropped on this basis — the caller adjudicates.
The stderr summary reports how many items were flagged. Pass `--no-hints` for
byte-identical passthrough when piping.

**4. The semantic pass — done by the model, not the script.** Even hints are
lexical, so a rewrite sharing no vocabulary at all — *"MCP just got its biggest
update ever"* against *"MCP retires sessions and the initialize handshake"* —
scores near zero and gets neither dropped nor flagged. This is why `SKILL.md`
requires pulling `ledger.py recent` and reading the survivors against it by
meaning before writing. The hints narrow that job; they do not replace it.

`new --verbose` prints what was dropped and why. This is worth scanning: if
something dropped is a genuine follow-up rather than a repeat, it is kept and
labelled as updating an earlier item.

### The window gate

`new` also drops candidates dated outside the window, which it derives the same
way step 1 does — from the profile's `last_run`, or the last 7 days if it has
never run — and prints on stderr. `--window-start` / `--window-end` override it
when the ask names a different span.

This is mechanical on purpose. The rule had been written into `SKILL.md`, moved
to the step that selects items, and had its contradiction removed; the next run
still headed a digest `2026-08-04 – 2026-08-11` and filled it with a conference
recap from March and another from June. Both items were recorded with their true
dates, so the model read the date, wrote it down, and kept the item anyway. A
rule the model must apply to itself does not hold.

The boundary is genuinely soft, though — `SKILL.md` step 1 lists four cases where
an out-of-window item belongs in the digest — so this is a filter, not a refusal:

- Exit status never changes. An out-of-window candidate is a filtered candidate,
  not a failed run, so `new && ...` still chains.
- Dropped items appear under `out_of_window` in `--verbose` output, each with the
  reason. That list is also exactly the set worth recording with `reason` in
  step 7, so the same stale story does not cost a judgement call every week.
- An item survives by naming which boundary case applies, in a `window_exception`
  field: `straddles-window`, `still-live`, or `first-run-context`. Any other
  value counts as no exception, so the field cannot be satisfied with prose.
- "Older news in fresh coverage" — the fourth case — has no code, because it is a
  rule to *drop* the item. That is what both failures were.
- A missing or unreadable `date` is kept and annotated `_date_unknown`, never
  silently dropped: a candidate may legitimately arrive undated and get its date
  when it is fetched. It is also not checked against the window, which is why
  `SKILL.md` step 4 puts any item whose date it establishes back through `new`.

`add` applies the same gate a second time, and there it refuses. Filtering was
the right answer in `new` — an out-of-window candidate is one that never enters
the digest — but it stopped short of the decision it was meant to govern:
`new` filters its own stdout, and nothing made the published set a subset of
that. An item dated twelve days before the window reached the ledger on a run
whose `new` call reported no drops at all, because it was introduced afterwards
and never passed to `new`. By `add` the digest exists, so dropping the item
silently would leave it published and unrecorded; refusing stops the chain
before delivery instead. Same field, same three codes, same derivation of the
window — a second checkpoint with its own vocabulary would only relocate the
argument.

---

## The ledger

State lives outside the repo, because it is user state rather than project code,
and follows the XDG Base Directory spec:

```
~/.local/state/ai-news-monitor/<profile>/
  ledger.jsonl    # append-only, one story per line
  state.json      # last_run, runs, last_window, interests
```

The root resolves in this order:

1. `--home PATH` — the flag, most explicit, wins outright
2. `AI_NEWS_HOME` — environment override
3. `$XDG_STATE_HOME/ai-news-monitor`
4. `~/.local/state/ai-news-monitor` — the XDG default

Most-explicit-wins: a flag beats an inherited environment because it is what the
caller typed on purpose. `--home` goes before the subcommand, alongside
`--profile`.

`XDG_STATE_HOME` is the right slot rather than `XDG_DATA_HOME` or a config
directory: the ledger is history — what was reported and when — which should
survive a restart but is not something anyone needs to back up or carry between
machines. Nothing here is tied to a particular agent or client.

An earlier version stored under `~/.claude/ai-news-monitor/`. If that directory
exists and the XDG one does not, the script keeps reading the old location and
prints a one-line notice on stderr, rather than silently starting an empty
ledger and re-reporting everything. Move the directory to clear the notice.

`ledger.jsonl` is append-only and tolerant: a torn line is skipped rather than
taking down the run. Each entry stores `url`, `canonical_url`, `title`, `beat`,
`date`, `source`, a short `why`, `duplicate_of`, `reason`, `window_exception`,
and `recorded_at`.

`duplicate_of` and `reason` mark entries the reader has effectively already
had — a restatement of a covered story, or news correctly ruled out by the
window. Items the ranking rejected on merit are deliberately *not* recorded:
suppression is permanent and untimed, and a preannouncement rejected today is
often the same URL that carries a ship date next quarter. `duplicate_of` names the story an item restates; `reason` covers
every other ground for exclusion, most often an item correctly ruled out by the
window — old news that is not a duplicate of anything and would otherwise
resurface in every future sweep. Recording them means
their URLs are suppressed by exact match forever, rather than having to be
recognised by meaning every week. `status` counts them as
`items_suppressed` and keeps them out of `items_published` and `by_beat`,
so they never inflate what the reader was told was covered. The same mechanism
handles one story arriving from several URLs: cite one, record the rest as
duplicates of it, never invent a synthetic combined URL.

### Commands

```bash
python3 scripts/ledger.py --home DIR status   # --home/--profile take either position, but are always flags
python3 scripts/ledger.py status              # last run, counts, beat breakdown, run dir
python3 scripts/ledger.py start-run           # empty and print this run's scratch dir (Step 1 only)
python3 scripts/ledger.py since               # just the last-run timestamp
python3 scripts/ledger.py new -i cand.json    # filter candidates down to unseen and in-window (-v shows drops)
python3 scripts/ledger.py new -i cand.json --window-start 2026-01-07   # same, for an explicitly asked span
python3 scripts/ledger.py add -i items.json --verified link-check.json   # record reported items, stamp the run
python3 scripts/ledger.py add --items '[{"url": "..."}]' --verified link-check.json   # same, inline
python3 scripts/ledger.py add --url URL --title "..." --verified link-check.json      # same, one item from flags
python3 scripts/ledger.py record-run          # stamp a run that reported nothing
python3 scripts/ledger.py config              # read this profile's standing interests
python3 scripts/ledger.py config --interests "..."   # set them
python3 scripts/ledger.py config --clear      # remove them
python3 scripts/ledger.py recent              # dump recent reports (default: LOOKBACK_DAYS)
python3 scripts/ledger.py forget --url URL    # drop a mis-recorded entry
```

`new` and `add` are the only subcommands that take items, and items are always
JSON: a list of objects, or an object with an `items` key. Only `url` is
required per item. `-i/--input` names a **file of that JSON**, not a rendered
digest — pointing it at the Markdown a run produced fails with `input is not
valid JSON` and records nothing. With no item flag and no `--input`, both read
the JSON from stdin.

`new` writes the unseen, in-window subset to stdout, so it pipes straight into
the next step. `window_exception` is read by both `new` and `add`, and stored by
`add`. Everything else — `status`, `start-run`, `since`, `record-run`, `config`,
`recent`, `forget` — takes no items at all; `forget --url` names the entry to drop
rather than describing one.

`start-run` is the only subcommand that touches the run's scratch directory, and
the only one that is destructive by design: it empties the directory so the run
starts from nothing. `status` reports the same path as `run_dir` and leaves it
alone, which is why the two are separate — `status` is the command a run repeats
to check its own work, including after `add`, and clearing from there would delete
the digest between recording it and delivering it.

`--profile <name>` keeps separate watch lists — a work profile and a personal one
do not pollute each other's history. It is accepted before or after the
subcommand, but only ever as a flag: a bare `ledger.py work status` is rejected.

---

## Layout

```
ai-news-monitor/
├── SKILL.md                    # model-facing: the 7-step workflow and rubrics
├── README.md                   # this file
├── references/
│   ├── beats.md                # 7 beats, query seeds, per-beat traps
│   └── sources.md              # where primary sources live, what to distrust
├── assets/
│   └── digest-template.md      # output structure
└── scripts/
    ├── check_links.py          # validate a finished digest's links (stdlib only)
    ├── ledger.py               # seen-story ledger (stdlib only, Python 3.11+)
    └── md_to_mrkdwn.py         # Markdown to Slack mrkdwn (optional, needs uv)
```

**The beats** — 1. agentic AI (frameworks, protocols, tool use) · 2. inference
and serving · 3. hardware and silicon · 4. model releases and capability shifts ·
5. evaluation and benchmarks · 6. infrastructure economics · 7. policy, safety
and security as deployment constraints. All seven are swept by default.

Beats are an internal organising device only. They shape what gets searched and
they are stored on each ledger entry for filtering, but they never appear in a
published digest — see [Write](#6-write).

---

## Customising it

- **Add or reshape a beat** — edit `references/beats.md`. Each beat is a scope
  paragraph, a list of query seeds, and a "watch for" note naming that beat's
  characteristic failure. Keeping that third part is what stops a new beat from
  filling the digest with press releases.
- **Change what counts as signal** — edit the Step 5 rubric in `SKILL.md`.
- **Change the output shape** — edit `assets/digest-template.md`.
- **Tune deduplication** — four constants at the top of `scripts/ledger.py`:

  | Constant | Default | Effect |
  |---|---|---|
  | `LOOKBACK_DAYS` | 45 | How far back the **title** comparison reaches, and the default for `recent`, so the two cannot drift apart. URL matching is unbounded and ignores this. Override per call with `recent --days N`. |
  | `TITLE_MATCH_THRESHOLD` | 0.72 | Similarity at or above which an item is silently dropped as a duplicate. |
  | `SUGGEST_THRESHOLD` | 0.22 | Similarity at or above which an item is kept but annotated with `_maybe_same_as`. |
  | `MAX_HINTS` | 2 | Hints attached per item. |

  Raising `SUGGEST_THRESHOLD` yields fewer, noisier-free hints; lowering it
  surfaces more candidate clusters at the cost of more to dismiss. Since hints
  never drop anything, erring low is the cheap direction.

  Lowering `TITLE_MATCH_THRESHOLD` is the risky one. The regression to re-run is
  that near-identical-but-genuinely-different headlines ("vLLM v1.1.0 adds FP4
  decode kernels" vs "SGLang v0.5 adds FP4 decode kernels", which score **0.60**)
  still survive as two items — higher than most real duplicates score, which is
  why the hint mechanism exists instead.

  Only `LOOKBACK_DAYS` is exposed on the CLI; the rest are edit-the-file
  settings, on the view that thresholds should be changed deliberately and with
  the regression re-run, not per invocation.

---

## Known limits

1. **Verification is instruction, not enforcement.** Nothing mechanically stops a
   run from writing a headline off a search snippet. The rubric makes it likely,
   not certain. Read the **Coverage notes** section for what a given run admits it
   did not check.
2. **No RSS or feed ingestion.** Discovery is entirely web search plus direct
   fetch, so it inherits those tools' behaviour — search results are US-region,
   and fetches are cached briefly.
3. **The 0.72 threshold is a tuned guess.** Verified in both directions on a small
   sample: it catches tense rewrites and does not merge distinct same-shape
   stories. It has not been tuned on a large corpus.
4. **Ranking is model judgment.** The rubric is explicit, but no score is computed
   and nothing audits the resulting order.
5. **Requires Python 3.11+.** Annotations evaluate at runtime rather than being
   deferred, and the code uses `datetime.UTC`. The floor is set above 3.10
   deliberately: 3.10 reaches end of life in October 2026.
6. **An unrecorded run silently breaks incrementality.** If Step 7 is skipped, the
   next digest repeats itself. `ledger.py status` is the way to check: `runs`
   should go up by one per digest.
