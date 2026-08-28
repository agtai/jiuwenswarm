# PR tracking digest skill — v1 design

Status: design only. Nothing here is implemented, no cron job is created, and no
existing skill or its state is modified. Written 2026-08-12; every factual claim
about the trackers was verified on that date and is recorded with its evidence
in the appendix.

This is a v1 meant to be built and iterated, not a settled specification. **All
four decisions v1 depended on are answered** (§17); what remains is deferred to
v2 and has a working default, so nothing here is blocked.

**The v1/v2 boundary in one line:** v1 registers links through the `url` trigger and
holds **no Slack credential**; v2 adds a `conversations.history` scan of record
via jiuwenswarm's own `slack_history` capability. §15 covers v1 and its known
coverage gap, §15.3 covers v2. Everything else — schema, watermark, rotation,
status model, reporting — is unaffected by that boundary and ships in v1.

## 1. What this is for

A Slack channel collects links to issues and pull requests. The skill maintains
a store of everything known about each tracked item, and on each cron tick posts
what *changed* since the last time it posted.

The cron decides *how often*. It does not decide *what is covered*: coverage is
always "everything since the last recap that was actually delivered". A tick
that fires after two days of downtime reports two days.

## 2. The central structural decision: track richly, report deltas

The store and the report answer different questions and must not share a shape.

- **The store holds the complete current state of every tracked item**, refreshed
  on every tick whether or not anything changed. It is a mirror of the trackers,
  not a report backlog.
- **The report names an item if and only if something about it changed** since
  the last *delivered* report.

Everything else in this design follows from that split. It is what makes the
watermark do real work, it is what makes "what do we post when nothing changed"
a non-question, and it is why the schema can be generous about what it records
without making the report noisy.

The one refinement on top of the operator's phrasing: **a single status column
is not enough.** One column cannot distinguish "changed, and the reader has been
told" from "changed, and the reader has not been told yet" — and those diverge
the moment a run fetches successfully but fails before delivery. So every
reportable field is stored twice:

| Column | Written by | Meaning |
| --- | --- | --- |
| `<field>` | the refresh phase, every tick | what the tracker says right now |
| `reported_<field>` | the commit phase, only after Slack has the report | what the reader was last told |

The delta is `field != reported_field`. That is the entire delta engine for
status, it is trivially inspectable in the file, and it self-heals: a run that
dies before delivery leaves `reported_*` untouched, so the next run reports the
same change rather than swallowing it.

## 3. Two entry points

The skill has two modes with different jobs, different failure tolerances, and
different callers.

### `track` — maintain the store

Registers, re-registers and unregisters items. Called from:

- a **`url`-trigger turn** — the only automatic path in v1 (§15);
- an **operator invocation** ("track this", "stop tracking that"), which may also
  run a **channel-history reconciliation** — from Slack only, never the CLI
  (§15.2).

`track` does **no tracker network calls and no
status refresh** — it writes identity and registration fields only. That keeps
it fast enough to run inside a `url`-trigger turn without making the bot's reply
wait on GitHub, and it keeps a registration path from ever being able to corrupt
status.

`track` is a pure upsert keyed on §4's identity key. Registering the same item
twice is a no-op on everything but `sources`. **One invocation may upsert several
rows** — a single Slack message routinely carries more than one link, and
the `url` trigger fires only once for it (§4.1). It writes to the store named in
that channel's link-trigger prompt, which must be the same store the cron prompt names
(§8.2).

### `report` — the cron tick

Refreshes every active row from both trackers, writes the new status into the
store, diffs against `reported_*`, renders, delivers, and only then commits
`reported_*` forward. §9.

It takes `--state-file` from its cron job description (§8.1), so one cron job per
channel also buys one schedule per channel.

`report --full` additionally renders the whole roster, for on-demand use;
`report --repo <owner/name>` filters it (§8.3). The cron uses plain `report`.

## 4. Identity: one row per change

Both registration paths, and both trackers, must land on the same row.

**The identity key is the canonical GitHub PR** when one exists, expressed as
`github/<owner>/<repo>#pr<N>`. Derivation:

1. Normalise the posted URL: lowercase scheme and host, drop query, fragment and
   trailing slash, reduce `/pull/2724/files`, `/pull/2724/commits`, and
   `#issuecomment-…` to the PR root.
2. A GitHub PR URL yields the key directly.
3. **A GitCode MR URL resolves to the same key**, because the sync bot names the
   MR's source branch `github-pr-<N>` (§6). Someone pasting the GitCode link
   gets the same row as someone pasting the GitHub link — which is exactly the
   dedupe case the operator's "both paths enabled" note creates, in its harder
   form.
4. A GitCode MR with no GitHub origin keys as `gitcode/<project>#mr<iid>`.
5. An issue keys as `…#issue<N>`.

Because every path computes the key from the URL before touching the store, the
same PR arriving from a `url`-trigger turn and later from an operator-run
reconciliation is one upsert and one row — which is what makes reconciliation
safe to run at any time, as often as wanted.

The row records **every** way it was registered:

```json
"sources": [
  {"via": "url",          "slack_ts": "1786514497.123", "url": "https://github.com/…/pull/2724",              "at": "2026-08-12T09:01:03Z"},
  {"via": "url",          "slack_ts": "1786514497.123", "url": "https://gitcode.com/…/merge_requests/4717",   "at": "2026-08-12T09:01:03Z"},
  {"via": "reconcile",    "slack_ts": "1786514497.123", "url": "https://github.com/…/pull/2724",              "at": "2026-08-12T10:00:00Z"}
]
```

`via` is one of `url`, `reconcile` (an operator-run history pass, §15.2)
or `operator` (an explicit "track this"); v2 adds `scan` (§15.3). Deduplicated on
`(slack_ts, url)` — **not on `slack_ts` alone**, for the reason §4.1 gives. A
reconciliation re-seeing a message the `url` trigger already handled adds nothing,
which is what lets every path run without coordination. This list is also what makes a wrong registration diagnosable: it says
which mechanism introduced the row, from which message, and via which of that
message's links.

### 4.1 One trigger, N items

The `url` trigger fires **once per message, however many links the message contains**.
The trigger is `_HTTP_URL_RE.search(text)` (`slack_connect.py:2177` on the
deployed tree) — a single match against the whole message body, not an iteration
over matches. Verified live 2026-08-12 16:44 UTC in `C0BPLSPHHDZ`: a two-link
message dispatched one turn, which made two `fetch_webpage` calls and covered
both items. The interim channel prompt says "the linked item", singular, and the
model generalised to both anyway — so **the plural case arrives whether or not
the prompt invites it, and the design cannot rely on the model making that leap
every time.**

Three consequences:

**Registration fans out.** One trigger yields N rows. `message_ts` is
**provenance, not identity**: all N items born from one message share it, so
anything keying a row or a dedupe check on `message_ts` alone collides and
silently collapses N items into one. Identity is §4's key — effectively the
tuple *(tracker, repository, number)* — and `slack_ts` only ever appears inside
a row's `sources[]`, alongside the specific `url` it came from.

**Mixed content in one message.** Each URL in the message is classified
independently, then the results are merged:

| Case | Behaviour |
| --- | --- |
| Two links to the same item (`/pull/2724` and `/pull/2724/files`) | Normalisation gives one key → one row, two `sources[]` entries. |
| A GitHub PR link **and** its paired GitCode MR link | §4 rule 3 resolves both to the same key → **one row**, not two. This is the case the `github-pr-<N>` branch convention exists to catch, and it is likely in a tracking channel where someone posts both sides of the same change. |
| A trackable link plus an unrelated URL (a doc, an article) | The unrelated URL is **skipped silently.** |
| A message whose URLs are *all* untrackable | Reported **once**, as "not tracked: no pull request or issue link", and a single `kind: other` row is stored so the dedupe key exists and the scan cannot resurface it. |

The asymmetry in the last two rows is deliberate and refines §7. Silence is
right when the message clearly did its job — commenting on every incidental link
would make the report noisy in exactly the channel where people paste context
alongside a PR. Speaking up is right when the message produced *nothing*, because
that is the mis-post case, and silently swallowing it is indistinguishable from
the skill being broken.

**Partial failure is per URL, not per message.** If a message carries three
links and one lookup fails, **the two that succeeded register, and the one that
failed is reported as failed** — never dropped, and never allowed to roll back
its siblings. The failed URL is recorded as a row with `lifecycle: active`,
`refresh_ok: false` and the error, so the next tick retries it naturally through
the ordinary refresh path; no separate retry queue is needed. An all-or-nothing
rule would be strictly worse: it would discard good registrations because of an
unrelated 404, and it would make a single bad link in a paste of five silently
cost the other four.

## 5. Status: rich model, quiet report

The uniformly-useless field is `mergeStateStatus`, which reads `BLOCKED` on every
open PR here forever (§18). That is a reason not to *lead* with it — not a reason
to thin out the status model. Two axes change and matter:

- **Conflict state.** Upstream moves and a previously-clean PR becomes
  conflicted. Verified live: PR #2455 was labelled `conflicted` at
  2026-08-12T07:49:52Z. This transition is precisely what the operator wants to
  hear about, and under §2 it is reported the tick after it happens and never
  again until it flips back.
- **Approval progress.** A change may need two `/lgtm` and have one. `lgtm_count`
  going 0→1 is real progress even though the merge button stays blocked forever.

The decision state lives on GitCode, whose label vocabulary carries it:

| Label | Meaning |
| --- | --- |
| `openJiuwen-cla/yes` | CLA satisfied for every commit |
| `ci-running` / `ci-successful` / `ci-failed` | pipeline state |
| `lgtm-<login>` | one per maintainer who ran `/lgtm` |
| `approved` | a maintainer ran `/approve` — the real merge gate |
| `github-mirror` | MR created by the sync bot from a GitHub PR |

The derived `status` enum, ordered:

```
registered → cla_pending → ci_running → ci_failed
           → awaiting_review   (CI green, no lgtm-*)
           → lgtm_partial      (≥1 lgtm-*, no approved)
           → approved          (approved present, not yet merged)
           → landed            (GitCode MR merged)
           → closed            (closed without landing)
```

with independently-tracked flags `conflicted`, `stale_ci`, `draft`, `gone`, and
the separate scalars `lgtm_count`, `ci_verdict`, `comment_count`.

`mergeStateStatus` appears once in the whole report, as a footnote constant
("GitHub reports every open PR as BLOCKED; the merge gate is a `/approve` on
GitCode"), and never in a row.

This model also produces a line the naive one cannot: an item whose GitCode MR
merged while its GitHub PR is still open has **landed**, and the GitHub PR is now
stale and wants closing by hand.

## 6. Mirroring: one row, two facets

Tracking only GitHub gives a report where nothing ever progresses. Tracking only
GitCode loses the link the operator posted and the timeline events. So one row
carries both facets.

**Pairing discovery**, verified for all eight of our open PRs:

1. The sync bot creates the MR on a branch named `github-pr-<N>`. PR 2724 →
   MR !4717, 2723 → !4716, 2720 → !4715, 2718 → !4714, 2669 → !4686,
   2455 → !4578, 2377 → !4531, 2095 → !4378.
2. Cross-check: `head.sha` is identical on both sides. True for all eight.
3. Neither matches → `pairing: none`, and the report says the GitCode side is
   unknown for that item rather than inventing one.

**Cost.** GitCode's `pulls` endpoint ignores the `source_branch` query parameter
(verified — it returns the unfiltered list), so discovery pages
`pulls?state=all&sort=created&direction=desc` until the branch or sha matches;
five pages of 100 reached our oldest open PR. This runs **once per item, ever** —
the pairing is immutable and cached in the row. Refreshes then hit `pulls/<iid>`.

**Do not generalise from the bot's own traffic.** Sync-managed PRs #2850, #2852,
#2854, #2855 all carry `mergedAt`; a human PR of ours never will.

### 6.1 How the skill reaches each tracker

**GitHub: `GITHUB_TOKEN` from the environment, read via a `--token-env` flag.
Deliberately not `gh`.** The variable is present to a skill script (D2), and the
flag spelling follows the sibling skill exactly —
`fetch_repository_activity.py:1135` takes `--token-env` defaulting to
`GITHUB_TOKEN` — so the variable name stays configurable rather than compiled in.

Two reasons this beats shelling out to `gh`, the second being the important one:

- **It is the mechanism already in production here.** The sibling skill runs on
  cron daily against this same repository with this same variable. A second skill
  inventing a second credential path would mean two things to keep working.
- **Least privilege, and it would be silently lost.** The operator created this
  token **deliberately more restricted than `gh`'s credentials**. `gh` is
  authenticated as a full account; a skill shelling out to it would quietly run
  with the *broader* set of permissions — not by anyone's decision, but as a side
  effect of which binary got called. Choosing the token keeps the narrower grant
  the operator actually intended, and keeps that choice visible in the command
  line rather than buried in `~/.config/gh/hosts.yml`.

Unchanged from the earlier draft, and both still load-bearing:

- **A missing or empty `GITHUB_TOKEN` is a hard stop** with a clear message,
  never a silent downgrade to anonymous calls. Anonymous is 60 requests/hour: it
  would exhaust partway through a tick and produce a half-refreshed report that
  looks complete, which is the failure mode this design most wants to avoid.
- **The token is never printed or persisted** — not in the report, not in the
  store, not in a log line. The sibling skill states the same rule.

**GitCode: anonymous HTTPS reads.** No credential at all; verified working
against `api.gitcode.com` (§18).

**Read-only, absolutely.** The skill must never comment, close, approve, merge,
label, push, or otherwise mutate anything on either tracker. Every call is a GET.
This is not a default the skill may relax under any circumstance — including "the
item is obviously stale and should be closed", which §5 explicitly produces as a
*report line for a human*, not an action. The token's scope is a backstop for
this rule, not a substitute for it.

**Slack: no credential at all.** v1 registers through the `url` trigger, which is the
host's own connector doing the work; the skill never authenticates to Slack.
§15 has the reasoning and §15.3 the v2 route, which keeps it that way.

## 7. Schema

One JSON object per line. All reportable fields are scalars — see §8.

**Identity and registration** (written by `track`)

| Field | Source | Notes |
| --- | --- | --- |
| `key` | derived | §4; the primary key |
| `url` | Slack | canonical, normalised |
| `kind` | derived | `pull_request` \| `issue` \| `other` |
| `sources[]` | Slack | how, when, and via which URL it was registered; dedupe on `(slack_ts, url)` (§4, §4.1) |
| `first_seen_utc` | Slack | message ts when known, else run time |
| `slack_permalink` | Slack | the message that introduced it — provenance, never identity (§4.1) |
| `slack_author` | Slack | who posted the link |
| `lifecycle` | derived | `active` \| `terminal_pending` \| `retired` \| `ignored` |

**Tracker facts** (written by `report`'s refresh phase, every tick)

| Field | Source |
| --- | --- |
| `title_source`, `title_rendered` | GitHub / derived (§16) |
| `author_login`, `created_at`, `head_sha` | GitHub |
| `gh_state`, `conflicted` | GitHub |
| `mr_iid`, `mr_state`, `merged_at` | GitCode |
| `cla_ok`, `approved`, `lgtm_count` | GitCode labels |
| `ci_state`, `ci_verdict`, `ci_failure_hint`, `ci_head_sha` | GitCode labels + artifact (§11) |
| `comment_count` | both |
| `last_activity_utc` | max of both sides |
| `last_refresh_utc`, `refresh_ok`, `refresh_error` | derived |

**Reported mirror** (written by `report`'s commit phase, after delivery)

`reported_status`, `reported_conflicted`, `reported_lgtm_count`,
`reported_approved`, `reported_ci_verdict`, `reported_comment_count`,
`reported_head_sha`, `observed_through_utc`, `last_mentioned_run`.

**Derived, not stored**: `status` (§5) is recomputed from the facts each tick —
storing it as well would create two sources of truth for the same thing.

The rotation marker the sketch asked for is `lifecycle`. §10.

## 8. Storage

**JSONL, one object per line, plus a sidecar `runs.json`.** Whole-file atomic
rewrite (temp file in the same directory, `os.replace`) under a
`portalocker.Lock` on a sibling `.lock` file — the pattern already in tree at
`jiuwenswarm/gateway/cron/store.py:140-153`, which guards `cron_jobs.json` with
`cron_jobs.json.lock` for exactly this situation: a scheduled writer and a
human-driven writer on one file.

The store location is a **parameter**, not a fixed path — §8.1.

### 8.1 Where the store lives: stated in the prompt, XDG by default

The house pattern, and the one this skill follows:

```
explicit --state-file  →  XDG-compliant default
```

The explicit value is supplied by **whichever prompt is driving the run**. The
flag is the single mechanism; the default is what happens when nobody names a
path.

```
--state-file <path>                          (whatever the prompt names — wins)
$XDG_STATE_HOME/pr-tracking-digest/…         (script default)
~/.local/state/pr-tracking-digest/…          (script default, XDG_STATE_HOME unset)
```

`XDG_STATE_HOME` is **not set** in this environment, so on this host the script's
default resolves through the `~/.local/state` fallback rather than the variable.
The fallback is therefore the branch that actually gets exercised here, and the
one that has to be right.

**What our prompts name**, absolutely, and the convention this establishes for
future skills:

```
$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/<skill-name>/
```

**verified writable** by an actual write-read-delete probe under that exact
path, not assumed — with one further level wherever one store per instance is
wanted. Here the instance is the channel, so the deployed tracking channel is:

```
$JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracking-digest/C0BPLSPHHDZ.jsonl
```

`--state-file` names **the ledger**; the two sidecars derive from its stem —
`C0BPLSPHHDZ.jsonl.lock` and `C0BPLSPHHDZ.runs.json` — exactly as
`gateway/cron/store.py:146` derives `cron_jobs.json.lock` from `cron_jobs.json`.
The prompt states one path, not three.

Prefer the environment variable over a literal `/home/jiuwenswarm/.jiuwenswarm`:
`JIUWENSWARM_DATA_DIR` is real and is the runtime's own resolution root
(`jiuwenswarm/common/utils.py:401-409`, twenty references across the package).

### Why the default is XDG, and why our prompts override it

**Genericity across harnesses — why the *script* defaults to XDG.** Which agent
runs the skill is not an assumption the design gets to make: Claude Code, Codex,
opencode, jiuwenswarm, openclaw and Hermes are all in scope, and more will
follow. An XDG-compliant default is the portable choice — every one of those
hosts runs on a system where `$XDG_STATE_HOME` or `~/.local/state` means the same
thing. A jiuwenswarm-shaped path compiled into the script would bake one host
into a skill with no reason to care.

**Two reasons the prompts override that default on *this* host.** Neither is
obvious, and both would be discovered the hard way:

1. **Sandbox reachability.** A sandbox's allowed roots fall back to
   `[workspace, project_root, cwd, *skill_roots]` — stated verbatim in agent-core
   `fix/sandbox-skill-roots-v2` (`b01280e5`). **The workspace is granted; a
   sibling directory under `agent/` is not.** Sandboxing is off in this
   deployment today, so a store outside the workspace works fine right now and
   would break the day it is switched on — the worst kind of latent fault,
   because nothing about the working system hints at it. This is why the path
   sits under `agent/workspace/` rather than, say, `agent/skill-state/`.
2. **Backup coverage.** The borg backup's `SOURCES` is
   `/home/jiuwenswarm/.jiuwenswarm /home/jiuwenswarm/.cache/jiuwenswarm`, and the
   exclude list reaches only `__pycache__`, `.checkpoint`, two SQLite databases,
   their wal/shm sidecars, and `*.lock`. **`~/.local/state` is not backed up at
   all.** So the XDG default is right for a generic host and wrong for this one:
   losing the watermark does not lose a little history, it re-registers and
   re-reports the channel's entire backlog (§8.2). Under
   `agent/workspace/state/` the store is covered by the existing backup with no
   change to it. Incidentally the `sh:**/*.lock` exclude is also correct for this
   layout — a lock file is exactly what should not be restored.

### Why `state/`, and why not the neighbouring directories

**XDG's vocabulary maps; FHS's does not.** `STATE` means *persists across
restarts, but is not config, not user data, and not cache* — which is precisely a
watermark plus a roster. The FHS alternatives are worse fits in both directions:
`/run` is volatile and cleared at boot, `/usr/share` is static read-only data.

`state/skills/<name>/` also mirrors the shape of the script's own XDG default
(`~/.local/state/<skill>/<channel>.jsonl`), so the two read as **one convention
with two roots** rather than as two competing conventions.

`workspace/state/` **does not exist yet** — this establishes the convention
rather than following one. The two existing neighbours were considered and
rejected:

- `workspace/projects/` is a registered *working* directory, carrying
  `work_mode` and git configuration in `agent/projects.json`. It is where work
  happens, not where state is kept.
- `workspace/memory/` belongs to the memory subsystem and has its own database
  and lifecycle.

**This also explains something the anchor skill's script does not explain about
itself.** Reading `fetch_repository_activity.py` alone, the state path looks
under-specified — the script takes `--state-file` and resolves a relative value
against a jiuwenswarm-specific base. The reason the path is not hardcoded is that
**it is stated in the prompt**: `repository-activity-digest`'s cron job
description carries its `--state-file` explicitly. The prompt is the portable
place to put a host-specific path, because the prompt is written for a
deployment while the script is written for every deployment. That is not obvious
from the script and is worth saying once here.

Two corrections this design does make to the anchor's practice, neither of which
touches the pattern itself:

- **State the path absolutely in the prompt.** The anchor's cron prompt names a
  *relative* `--state-file memory/repository-activity-….json`, which resolves
  against a base invisible in the path itself — and that is exactly how a stale
  5.4 MB orphan came to sit at `workspace/memory/…` while the live state lives at
  `workspace/projects/memory/…` (§18). An absolute path in the prompt cannot
  develop a second interpretation.
- **Keep working files out of the skill directory.** Adopt
  `reject_path_in_skill_dir()` from `ai-news-monitor/scripts/ledger.py:220-238`
  for `--state-file`: that directory is shared by every run and is overwritten
  wholesale by the next sync, and there is a real incident behind the guard.

`ledger.py` is corroboration rather than a competing pattern: its `home()`
resolves `--home` → `AI_NEWS_HOME` → `XDG_STATE_HOME` → `~/.local/state/…`, which
is the same explicit-then-XDG order in a different spelling.

### 8.2 How the two entry points learn the path — and the failure this creates

**They learn it the same way: from their own prompt text.**

- `report` takes `--state-file` from its **cron job description**.
- `track` takes `--state-file` from the **link-trigger prompt** for the channel —
  the per-conversation rule that already names `C0BPLSPHHDZ` (§15.4).

Both name the same string:

```
--state-file $JIUWENSWARM_DATA_DIR/agent/workspace/state/skills/pr-tracking-digest/C0BPLSPHHDZ.jsonl
```

Multiple channels therefore means multiple cron jobs, each prompt naming its own
store — which buys **per-channel schedules for free**: one project daily, another
weekly, without the skill knowing anything about channels.

**The failure mode is that the two prompts disagree.** This replaces the silent
divergence of a derived scheme with a different, equally quiet problem, and it is
the one thing about this design most likely to go wrong in practice:

> If the link-trigger prompt names one store and the cron prompt names another,
> registration writes one file and the report reads a different, permanently
> empty one. **Nothing errors.** The channel fills with links, every registration
> appears to succeed, and every report says "0 tracked, none changed" forever.

Both prompts must carry the **same path**, and it must be written the same way in
both — an absolute path in one and a relative path in the other are two stores
even when they look equivalent.

Because prompt discipline is not enforceable by the skill, the report is made to
disclose what it actually read:

```
_12 tracked · since 08:00 · store: …/state/skills/pr-tracking-digest/C0BPLSPHHDZ.jsonl (12 rows)_
```

That one line is cheap and converts an invisible failure into an obviously wrong
report: a store path nobody recognises, or `(0 rows)` under a channel that has
been collecting links all week, is immediately legible as a misconfiguration
rather than as "nothing happened". A report that cannot be trusted to be
*visibly* wrong when it is wrong is worse than no report.

Two further cheap guards, in order of value:

- **Never start fresh silently.** If the named store does not exist, say so
  before creating it. An empty ledger is not a neutral state — it re-registers
  and re-reports every link in the channel's history. `ledger.py` encodes the
  same lesson when it reads its legacy location rather than starting over.
- **Record the owner.** `runs.json` carries `channel_id` and the cron `job_id`
  (§9, available per D3). An opener asked to serve a different channel stops and
  writes nothing. This does not catch the disagreeing-prompts case — a fresh
  empty store has no owner to disagree with — but it does catch a cron prompt
  edited to point at another channel's store, which would otherwise interleave
  two channels into one ledger with each retiring the other's items as
  unrecognised. Recording `job_id` also makes "which cron job last wrote this
  store" answerable from the store itself.

### 8.3 Per channel, not per repository

One store serves **one channel**, and repository is a *column*, not a file — even
though one channel may carry links from several repos.

- One prompt names one path. Keying by repository would mean the link-trigger
  prompt naming a path it cannot know in advance — the repo is only discoverable
  after the URL is parsed — and would leave `report` unioning a set of stores
  that changes silently whenever someone posts a link to a new repo.
- The watermark is a property of a **report stream**, not of a repository.
  `reported_*` and `last_completed_run_utc` describe what *this channel's readers
  were last told*. Splitting by repository would fragment one report's watermark
  across N files that then have to be committed atomically together —
  reintroducing the multi-file transaction §9 is built to avoid.
- A per-repository *view* is a filter, not a storage layout: `report --repo
  <owner/name>` reads the one store. §9's commit rule already makes this correct
  without modification, because it advances `reported_*` only for items that
  **appeared in the delivered report** — so two repo-filtered jobs against one
  channel do not consume each other's deltas.

The one adjustment that needs stating: with filtered reports, `runs.json` keys
its run bookkeeping by `stream` (the filter, defaulting to `all`) so two filtered
jobs do not clobber each other's `last_completed_run_id`.

**On CSV.** Now that §2 has reduced every reportable field to a scalar, the
operator's instinct is very nearly right and the gap is small. JSONL still wins
on two counts, both cheap: a new field is a new key on new rows rather than a
column added to every row and every reader, and the couple of naturally-listy
fields (`sources[]`, a sample of failing test ids) do not have to be flattened
into a separator-delimited cell that rots the first time a value contains the
separator. Neither is decisive at tens of rows. **This is a reversible choice** —
the schema is flat enough that converting either direction is a short script, so
it should not hold up v1.

**On SQLite.** Disproportionate here — tens of rows, read and rewritten whole,
once per tick — and it works against §12, where the correction path is *the
operator opens the file and fixes it*.

**Concurrency.** `track` from a `url`-trigger turn and `report` from the cron can
genuinely collide. Both take the lock for the whole read-modify-write. The lock
is never held across a network call or across report delivery; §9 splits the run
into two short locked phases with the slow work in between.

## 9. Watermark, delta, idempotency

### No timeframe, anywhere

The skill accepts no `--hours` and no window. Two delta sources:

1. **Field diff** — `field` vs `reported_field` (§2). This is the primary
   engine, it needs no timestamps at all, and it is automatically correct across
   a missed run: `reported_*` is whatever the reader was last told, however long
   ago that was.
2. **Event watermark** — `observed_through_utc` per item, for activity that has
   no status field: new comments, pushes. Delta is activity in
   `(observed_through_utc, run_cutoff_utc]`.

`run_cutoff_utc` is captured **once** at the start of the run and used for every
item, so activity arriving mid-run belongs to the next report rather than
falling in a racy gap.

**A missed run self-heals with no special case.** Two days down means every
`reported_*` is two days stale and every `observed_through_utc` is two days old;
the next tick's deltas are two days wide. Nothing has to know a run was missed.
That is the whole reason a watermark beats a window — a window would report one
day and lose the other, silently.

An item with `observed_through_utc: null` is new: it reports as a registration
with its current state, not as a backfill of history from before it was tracked.

### `runs.json`

```json
{
  "schema_version": 1,
  "channel_id": "C0BPLSPHHDZ",
  "cron_job_id": "b5780cc9cdc74c50b194d9321a182b0f",
  "streams": {
    "all": {
      "last_completed_run_utc": "2026-08-12T06:00:07Z",
      "last_completed_run_id": "cron-19ff48e6310",
      "last_attempt_utc": "2026-08-12T07:00:02Z",
      "pending": null,
      "consecutive_failures": 0
    }
  }
}
```

`channel_id` and `cron_job_id` are the owner record of §8.2, checked before any
write; both come free from the cron metadata (D3). `streams` is keyed by report
filter (§8.3) so a repo-filtered job keeps its own bookkeeping. v2 adds one more
field here, `history_scanned_through_ts` (§15.3).

### Run sequence

1. **Locked, short.** Read `runs.json` and the ledger. **Verify `channel_id`
   matches the channel being served; on a mismatch, stop and write nothing**
   (§8.2). If this stream's `last_completed_run_id` equals this run's id, exit
   without posting — a retry of a run that already delivered. Stamp `pending`.
   Release.
2. **Unlocked, slow.** Refresh every `active` row from both trackers. Classify
   CI where needed. Write the refreshed facts into the ledger (a short locked
   write; `reported_*` untouched). Compute deltas. Compose the report. (v2 adds
   a channel scan at the head of this step — §15.3.)
3. **Deliver to Slack.**
4. **Locked, short.** For every item that refreshed successfully *and* appeared
   in the delivered report, copy `field → reported_field` and set
   `observed_through_utc = run_cutoff_utc`. Apply rotation transitions (§10).
   Set `last_completed_run_utc` / `last_completed_run_id`, clear `pending`.
   Release.

### Consequences, stated plainly

- **At-least-once, never at-most-once.** A crash between 3 and 4 repeats that
  delta next run. Duplicated news is recoverable by a reader; lost news is not.
  This is the deliberate direction of the trade — and the opposite of the anchor
  skill's, which commits its watermark inside the fetcher, before the model has
  composed anything (§18).
- **Refreshing the facts is safe to do eagerly**, precisely because it does not
  touch `reported_*`. The store can be as current as it likes; only delivery
  moves the reporting frontier.
- **A failed refresh advances nothing for that item.** Watermarks are per item so
  one unreachable tracker cannot consume the whole roster's window.
- **A double-fire is suppressed exactly**, not on a best-effort basis. D3 is
  answered: the scheduler passes `metadata={"cron": {"job_id": job.id, "run_id":
  ev.run_id}}` (`scheduler.py:766`, with the same pair as `params` at `:352`), so
  a repeated `run_id` is a no-op against the persisted
  `last_completed_run_id`.
- A `pending` left over from last run means it died mid-flight. The next run says
  so under coverage and proceeds; the watermarks it finds are already correct.

## 10. Rotation and lifecycle

```
active ──(terminal observed)──▶ terminal_pending ──(reported once)──▶ retired
   ▲                                                                    │
   └────────────────(reopened, or URL re-registered)────────────────────┘
```

- **Terminal** is: GitCode MR merged (**landed** — the meaningful one), GitCode
  MR closed, or the GitHub PR closed. Decided GitCode-first, because our GitHub
  PRs get closed for reasons unrelated to whether the change landed.
- `terminal_observed_utc` is stamped on entry to `terminal_pending`. The item
  appears once in the next report's **Closed and landed** section; that run's
  commit phase moves it to `retired`.
- **Retired rows are kept, never deleted.** In order of weight:
  1. The row is the dedupe key. The Slack message is still in the channel; a
     deleted row means the next reconciliation re-registers the item, reports it,
     retires it, deletes it, and repeats forever.
  2. Reopen. A retired item seen open again — or whose URL is re-posted — is
     revived: `retired_at_utc` cleared, `reopen_count` incremented, `lifecycle:
     active`, original `first_seen_utc` preserved. It reports as *reopened*,
     which is a different and more interesting fact than *newly tracked*. A
     deleted row cannot tell the two apart.
  3. `first_seen_utc` → `terminal_observed_utc` is the only record of how long
     the item took.
- Retired rows are excluded from refresh, so they cost nothing per tick.
- **Pruning** is available and off by default: a row retired for more than N
  *completed runs* (not days — the no-timeframes rule applies here too) may be
  compacted to a tombstone keeping `key`, `url`, `first_seen_utc`,
  `retired_at_utc`, `reopen_count`. At the expected volume, never prune.
- **Absence is never terminal.** An item that vanishes from the tracker is
  `gone` (§14), not merged. An item missing from a truncated reconciliation is not
  retired at all.

## 11. CI: always surfaced, annotated when we can

**A CI failure is actionable whichever cause it has**, and the report always
surfaces it. A flaky failure means retrigger, or raise it with the reviewers; a
genuine failure means rework the change. Both are work. Nothing here suppresses,
filters, or downgrades a red build — the classifier exists to tell the reader
*which kind of work it is*, and it is a hint, never a gate.

`ci_verdict` is `pass` | `fail` | `running`. When it is `fail`, a separate
`ci_failure_hint` carries `matches_known_flake` | `unrelated_to_known_flake` |
`unclassified`, and the report renders, for example:

> `#2455` — **CI failed** · matches the known `example.com` flake signature
> (1 test) → retrigger, or raise with maintainers

> `#2718` — **CI failed** · 2 failing tests, no known-flake signature → likely
> needs rework

> `#2720` — **CI failed** · could not classify (report unavailable)

Under §2 a red build is named on the *transition* to red, and again on any change
to the failing-test set or the hint. §13 adds the re-surfacing rule that stops a
long-red item from going quiet forever.

### Where CI actually comes from

Not GitHub Checks: `statusCheckRollup` on #2724 has one entry, `license/cla`. The
pipeline runs GitCode-side and reaches GitHub two ways:

1. A comment from `openjiuwen-collaboration-bot` prefixed
   `<!-- bot2-ci-writeback -->`, with a `head_sha:` line, a result table, and
   artifact links.
2. The `ci-running` / `ci-successful` / `ci-failed` label triad from
   `openjiuwen-ci-bot`, **timestamped in the issue timeline** — so CI history is
   available as dated events, not only as a current value.

`head_sha` gives a free staleness check: differing from the PR's current head
means the green label describes an older push. That is `stale_ci`, and it is a
reportable field of its own.

### The classifier

The writeback links `…/jiuwenswarm/ut/<N>/unit_test_report.html`, where `<N>` is
the **GitCode MR iid** (verified: PR 2724 → MR !4717 → `…/ut/4717/…`). Fetchable
without credentials (HTTP 200, ~4.5 MB), pytest-html v4.2.0, with every result in
a `data-jsonblob` attribute — 4 742 records with `result`, `testId` and failure
text. Fully machine-readable.

**Match the failure signature, never the test name.** The known flake's victim
rotates: three tests dial `example.com`, leave an httpx socket unclosed, and the
resulting `ResourceWarning` becomes a `PytestUnraisableExceptionWarning` that
fails whichever *unrelated* test was running under `filterwarnings = error`. A
test-name allowlist would be wrong on its first run. The signature is the warning
class plus the unclosed socket, and the signature list lives in a reference file
the operator can extend when a new flake appears.

`unclassified` is printed as unclassified. Calling an unfetchable report a flake
is the one outcome worse than saying nothing.

**Cost control.** Fetch only when `ci-failed` is present *and* the head sha
differs from `ci_head_sha`; cache the verdict against that sha. At most one
4.5 MB fetch per failing push, not per tick.

## 12. Untracking and correction

1. **`track --unregister <url|key>`** sets `lifecycle: ignored`. The row is never
   reported and never re-registered, while still holding the dedupe key so a scan
   cannot add it back. This is the supported "I posted that by mistake" answer,
   and it is why §8 wants a format a human can also fix by hand. It takes a URL
   or a key and **never a message**, because one message may have produced
   several rows (§4.1).
2. **Edit the ledger.** One object per line, stable `key`. `grep`, fix, save.
   Covers everything the CLI does not: wrong classification, wrong pairing, a bad
   title rendering.
3. **A designated Slack reaction** (proposal: `:x:`) on the original message maps
   to `--unregister`. Read-only, visible to the channel, reversible by removing
   the reaction. Two things keep it out of v1: reactions are only visible during
   an operator-run reconciliation until the v2 scan exists (§15.3), and §4.1's
   ambiguity stands regardless — a reaction addresses a *message*, which may
   stand for several rows, so it cannot express "untrack the second of these
   three". The second is a semantic question needing an answer before it ships,
   not merely an access problem that v2 solves.

Deleting the Slack message does **not** untrack: registration is a recorded fact,
and a deleted message would just leave a row nothing can explain.

**Nothing here mutates a tracker.** No comment, no label, no close, no approve, on
GitHub or GitCode. Untracking is a local store operation only.

## 13. Report shape

Delta-only. The cron report names an item if and only if one of its `reported_*`
mirrors disagrees with the current fact, or it has activity past its
`observed_through_utc`.

Sections, in order, each omitted when empty:

```
*Tracked changes — <date>*
_<N> tracked · since <last delivered report, as a clock time and an elapsed span> · store: <path> (<N> rows) · registration: link trigger only_

*Newly tracked*          ← registrations since the last report
*Changed*                ← the delta, ranked by impact
*Closed and landed*      ← rotation, once per item
<!-- jiuwenswarm:slack-thread-details -->
*Detail* / *Coverage and gaps*
```

**Impact ranking**, highest first: landed → newly `conflicted` → CI went red →
newly `approved` → `lgtm_count` rose → CLA state changed → `stale_ci` appeared →
CI went green → new maintainer comment → author push.

**Rendering.** Block Kit tables are available and validated
(`blockkit_tables: auto`), so a Markdown table in the reply renders natively with
no marker (`slack_connect.py:3193-3198`); limits are 100 rows, 20 columns,
10 000 table characters, 50 blocks per message (`slack_blocks.py:49-53`). Use a
table when the *Changed* section has enough rows to benefit — say four or more —
and bullets when it has one or two, where a two-row table looks silly. Same for
*Closed and landed*. This is a departure from the sibling skill's
`slack-report-format.md`, which forbids tables; that rule predates Block Kit
table support.

### The three edge cases

- **Nothing changed.** One line: "12 tracked, none changed since 08:00." **Post
  it.** A silent tick is indistinguishable from a broken cron, an expired token,
  or an empty roster, and the failure this design most wants to avoid is the
  operator reading a stopped skill as a quiet one. One line per day is a cheap
  heartbeat. `report --full` gives the roster on demand.
- **Everything changed.** Cap the narrative, put the remainder in a table, and
  say what was left out of the narrative and why. Never truncate silently; if the
  table itself would exceed the limits, move it to the thread and say so.
- **Tracker unreachable.** Advance nothing, retire nothing. Post the items that
  *did* refresh, then an explicit line: "GitHub API unreachable at HH:MM; N items
  not refreshed, their state below is as of <time>." If only one tracker is down,
  refresh and report the other and mark only the affected facet — a GitCode
  outage costs the decision state, not the roster. Cached state is never
  presented as current.

### Re-surfacing

Delta-only reporting has one failure mode worth closing in v1: an item that goes
red and *stays* red is mentioned once and then never again. So an item in an
attention-needing status (`ci_failed`, `conflicted`, `cla_pending`) is
re-surfaced when `last_mentioned_run` is more than N completed runs old, in a
compact **Still waiting** line rather than the full narrative. N counts runs, not
days. Default proposed: 7.

## 14. Failure modes

| Failure | Behaviour |
| --- | --- |
| GitHub rate limit | Authenticated via `GITHUB_TOKEN` at 5 000/h against ~3-4 calls per item per tick — a non-issue at this size. Anonymous would be 60/h and unusable, so a missing token is a hard stop, not a fallback (§6.1). |
| GitCode rate limit / 5xx | Anonymous reads work today, no documented limit found. 429/5xx → "GitCode unreachable": decision state unavailable, GitHub facet kept, coverage says so. |
| PR deleted | 404 → `gone`, reported once, then retired. Row kept. |
| Repo private or invisible to the token | Also 404, **indistinguishable from deletion**. Report as `inaccessible`, naming the repo — never as "deleted". Visibility follows the token's grant (§6.1), which is deliberately narrower than the operator's own account, so this case is expected rather than exceptional. |
| Link is not a PR or issue | `kind: other`, `lifecycle: ignored`. Reported once **only if no other URL in the same message was trackable**; otherwise skipped silently as incidental context (§4.1). |
| One URL of several fails to resolve | The others still register. The failed one becomes a row with `refresh_ok: false` and is retried by the next tick's ordinary refresh. Never all-or-nothing (§4.1). |
| Slack message deleted after registration | Row persists (§12). |
| Unknown tracker label | Carried through as unknown rather than mapped onto a status; listed under coverage. |
| Corrupt ledger line | Skip it, leave it in place, report the line number. Never rewrite a file that did not fully parse. |
| **The link-trigger prompt and the cron prompt name different stores** | Nothing errors: registration writes one file, the report reads another that is permanently empty. The report's header discloses the store path and row count so this reads as an obviously wrong report rather than as silence (§8.2). The only real fix is prompt discipline. |
| Store belongs to another channel | `runs.json`'s `channel_id` disagrees with the channel being served → stop, write nothing (§8.2). |
| Named store does not exist | Say so before creating it. An empty ledger re-registers and re-reports the channel's entire history, so it is never a silent default (§8.2). |
| `--state-file` points inside the skill directory | Refused, per `reject_path_in_skill_dir` — that path is shared by every run and overwritten by the next sync (§8.1). |
| Two writers racing | portalocker on both short phases; no lock held across network calls or delivery. |

## 15. Registration: the `url` trigger in v1, a scan in v2

**v1 registers through the `url` trigger and nothing else. The skill holds no Slack
credential of any kind.**

This is a scope decision, not a capability limit — §17 D1 records that
`SLACK_BOT_TOKEN` *is* reachable from a skill script. The decision is to not
reach for it:

- **Slack access already exists inside the host.** jiuwenswarm has a Slack
  connector and a `slack_history` capability. A second, parallel Slack client
  living in a skill script would be a duplicate route to something the host
  already owns — and the right fix is to make the host's own route reach the
  cron turn (§15.3), which also repairs `repository-activity-digest`.
- **GitHub access does not exist in the host, so it must be supplied.** That
  asymmetry is the whole rule: *borrow what the host already has; supply only
  what it lacks.* `GITHUB_TOKEN` stays (§6.1) precisely because there is no
  jiuwenswarm↔GitHub connection to borrow.
- **It keeps the skill portable.** §8.1 defaults to XDG so the skill can travel
  to Claude Code, Codex, opencode, openclaw or Hermes. A skill that carried Slack
  credentials out of one harness's `.env` would not travel anyway — the
  credential-free version is the one that survives the move.

**The `url` trigger** — from `jiuwenswarm/gateway/channel_manager/im_platforms/slack/slack_connect.py`:

- Fires **once per message, not once per link**: the trigger is
  `_HTTP_URL_RE.search(text)` (`:2177` deployed), a single match on the whole
  body. N links produce one turn. §4.1 has the consequences, which are the
  largest of any item in this list.
- Fires **only on human messages**: `:2345` drops any event with `bot_id` or
  `bot_profile`, so a link posted by a GitHub integration or webhook never
  triggers it.
- Fires **only on new messages**: `_USER_CONTENT_SUBTYPES` is `{"file_share"}`
  (`:81`), so `message_changed` is discarded — a link added by editing, or a
  corrected link, never registers.
- Is **claimed by group mode first**: with `group_chat_mode: all` the URL branch
  at `:2010` is unreachable, because `GROUP_MODE_ALL` returns at `:2004`.
- Produces **an ordinary agent turn** (`:2393` appends the channel's prompt and
  dispatches normally), so registration is a best-effort model action and the
  turn also replies in channel — a visible bot message per posted link.
- Has **one prompt per channel**: a connector-wide default plus a single
  per-channel override, so the tracking channel carries a register instruction
  *or* an analyse-the-link instruction, not both.

In v1 every one of those is a real limit on what gets registered. §15.3 is what
removes them.

### 15.1 The v1 coverage limit — accepted knowingly, with a named remedy

**A link posted while the service is down does not register.** The `url` trigger
is event-driven: it reacts to a message as it arrives, and a message that arrives
while nothing is listening is not replayed. Nothing in v1 detects the omission
either, because the item never entered the store to have a watermark.

The same applies permanently in v1 to that trigger's other blind spots: a link
posted by an integration or webhook (`bot_id` messages are dropped), and a link
added by *editing* an existing message (`message_changed` is discarded).

**Remedies, in the order to try them:**

1. **Repost the link.** Immediate, costs nothing, and works because §4's identity
   key makes a re-registration an upsert rather than a duplicate.
2. **Ask the skill to track it** — `track` accepts an explicit URL from an
   operator (§3).
3. **Run a reconciliation from Slack** (§15.2), which reads the channel history
   and picks up everything missed.
4. **v2** (§15.3), which removes the limitation rather than working around it.

The report's coverage line carries `registration: link trigger only` on every run,
so a reader is never left to infer that a quiet channel means a quiet week. That
line disappears in v2.

This is a known, bounded limitation with four ways out, not a defect. It is
recorded here plainly so that nobody later mistakes an empty report for a broken
skill — or for a complete one.

### 15.2 Operator-invoked reconciliation — **from Slack, never from the CLI**

An operator invoking the skill **in the Slack channel** gets an ordinary Slack
turn, which carries `slack_channel_id` and — with `history_digest_channel_ids`
set to `["*"]` — `slack_history_digest_allowed`. The trusted history tool is
therefore available, and the skill can reconcile the store against the full
channel history.

> ⚠️ **This must be run from Slack.** A CLI invocation (`jiuwenswarm chat …`) is
> not a Slack turn: it fails the same gate for the same reason a cron tick does,
> so the history tool is never registered. The reconciliation then finds no
> history tool and returns **an empty result that is indistinguishable from an
> empty channel** — a silent wrong answer, not an error. If reconciliation is
> ever run from the CLI, it must detect the missing tool and say so rather than
> reporting zero.

Reconciliation is idempotent: §4's identity key makes re-seeing a known link a
no-op, and §10's retired rows stop finished items being resurrected. It is safe
to run as often as wanted.

### 15.3 Deferred to v2: the scan of record

**What v2 is, concretely.** Not "add a Slack client to the skill" — instead,
*let the host's existing capability reach a scheduled turn*, so the skill keeps
using `slack_history` and gains nothing to authenticate with.

The gate is `_filter_slack_history_request_metadata`
(`interface_deep.py:395-407`) and it tests three things. **A cron envelope
already passes the first**: `scheduler.py:54` sets
`channel_id = (job.targets or …)`, so a `targets: slack` job arrives with
`channel_id="slack"`. Only two fields are missing, and both are derivable at
dispatch:

| Missing field | Where it comes from |
| --- | --- |
| `slack_channel_id` | the job's own target channel — already known to the scheduler |
| `slack_history_digest_allowed` | a pure function of connector config: `"*" in history_digest_channel_ids or channel_id in history_digest_channel_ids` (`slack_connect.py:2453-2456`) |

So v2 is: **have the channel manager enrich a `channel_id="slack"` envelope with
those two fields, using the same check the connector already applies.** No new
trust model, no relaxed gate, no credential anywhere — and it repairs
`repository-activity-digest` in the same stroke, which today cannot read history
on its own cron either.

**Why the gate is the right thing to satisfy rather than route around.** It
exists to stop a *model* naming an arbitrary channel. An operator-written
`--channel` argument alongside `--state-file` would reach the same guarantee by
another route, which is why a token-based scan would have been *safe* — it simply
is not the route being taken. Recording this because it is the reason to prefer
v2's shape, not merely to postpone v1's.

**Scan machinery, designed and held for v2:**

- **Its own watermark**, obeying §9's no-timeframes rule: `history_scanned_through_ts`
  in `runs.json`, holding the Slack `ts` of the newest message already scanned —
  a message timestamp, not a wall clock, so it is directly comparable with what
  the history call returns. Each run reads forward from it, so a run after two
  days down scans two days. Committed **after** the run succeeds, like every
  other watermark here, so a crashed scan re-reads rather than skips. It is the
  one watermark safe to advance when nothing was registered: the messages were
  still examined.
- **Sees what the `url` trigger cannot** — bot and app messages, and edited messages.
- **Idempotent over the whole channel.** Re-scanning from `ts: 0` is always safe,
  so "rescan everything" is a legitimate repair rather than a dangerous one.
- **Failure modes that belong with it**, held here rather than in §14: a Slack
  rate limit (`conversations.history` is Tier 3) pages with backoff and, if it
  cannot finish, commits only the watermark it actually reached — a partial scan
  is correct, merely shorter. `not_in_channel` fails the scan outright and **must
  not** advance the watermark, since the messages were never examined. A
  truncated free-plan history is carried into the coverage line verbatim and
  never used to retire an item for absence.

When v2 lands, the scan becomes the path of record and the `url` trigger becomes a fast
path that is *allowed* to miss things — its blind spots stop being limits on the
skill and become the reason the scan exists.

### 15.4 The link-trigger reply, and why registration must not parse it

The interim prompt deployed in `C0BPLSPHHDZ` asks for eight named fields, one per
line — Tracker, Repository, Number, Title, Author, State, Created, Last activity
— with `unknown` permitted for any of them, plus a single line for a link that is
not a pull request or an issue. It is written in the singular throughout and
emits one field block.

**Shape for N items.** One block per item, and with N ≥ 2 a table is the better
rendering — one row per item, one column per field, which Block Kit renders
natively under `blockkit_tables: auto` (§13). Each block or row must begin with
the **canonical URL** of the item it describes, so segmentation is explicit
rather than inferred from blank lines. For a message whose links are all
untrackable, one line per URL rather than one line for the message.

**Registration must not parse that reply.** Two reasons, and the second is
decisive:

1. The prompt permits `unknown` for every field, **including Number**. A key
   built from *(tracker, repository, number)* is therefore not guaranteed to
   exist in the reply at all, and a row keyed on `unknown` is worse than no row.
2. The URL is already known, exactly and without inference — the skill matched
   it in the raw message text. Deriving identity from prose the model
   reconstructed *from* that URL adds a lossy step to something that was already
   certain.

So: **the script re-scans the raw message body with the same URL pattern and
registers from the matches; the model's reply is for human readers.** Under §3's
split, `track` does no network calls anyway, so the fields the prompt extracts
are not what the store is populated from — `report`'s refresh phase fetches them
authoritatively on the next tick.

This keeps model output entirely off the critical path. The interim prompt
remains useful as an immediate human-readable acknowledgement in the channel, and
it is worth pluralising so its output stops contradicting what the channel
actually receives — but nothing in the store should depend on it.

## 16. Output language

`preferred_language` is `en`. A sibling digest has produced mixed English and
Chinese in production, and the cause is visible in the data this design
collected: most bot comments and a large share of titles on the GitCode side are
Chinese — "变更摘要", "防投毒检查", "解决中断续跑从头开始问题". Pasting a tracker title
straight into a report reproduces that failure exactly.

Three measures, none naming a language pair:

1. **Resolve the output language once, before writing**: an explicit request,
   else `preferred_language` from `$JIUWENSWARM_HOME/config/config.yaml` (or
   `~/.jiuwenswarm/config/…`), else English. No second, private notion of "the
   report's language".
2. **Store both forms.** `title_source` verbatim for diagnosis, `title_rendered`
   in the output language, computed once at first refresh and cached. The report
   shows `title_rendered`; the source appears once in the thread detail, not on
   every mention. This is both the language fix and what keeps a table cell
   narrow — the sibling skill's "render it, original in parentheses" rule is right
   for prose and unusable in a cell.
3. **Gate on the existing checker.** Write the report to a file exactly as it
   will be delivered and run
   `repository-activity-digest/scripts/check_report_language.py` on it. **Reuse
   it, do not fork it.** A non-zero exit is fixed by rendering, never by deleting
   the offending item.

## 17. Decisions, all answered

**Nothing in this design is now blocked on an operator decision.** The four
questions v1 depended on are closed; what remains is listed as deferred, and each
deferred item has a working default so none of them holds up building.

| # | Question | Answer |
| --- | --- | --- |
| D1 | Can a skill script read `SLACK_BOT_TOKEN`? | **Yes — and v1 deliberately does not use it.** Both Slack tokens are reachable from a script a skill launches, so a token-based scan would work and would be safe. The operator's decision is to borrow the host's existing `slack_history` capability instead of running a second Slack client from a skill (§15), which keeps the skill credential-free and portable. v1 therefore registers via the `url` trigger only, with a real coverage gap (§15.1) and a concrete v2 that closes it (§15.3). |
| D2 | Is GitHub reachable, and how? | **Yes, via `GITHUB_TOKEN` from the environment**, read through a `--token-env` flag following the sibling skill's spelling. Not `gh` — the token is deliberately more restricted than the account's `gh` credentials, and shelling out would silently widen the grant (§6.1). Read-only remains absolute. |
| D3 | Does the skill see `cron.run_id`? | **Yes.** `scheduler.py:766` builds `metadata={"cron": {"job_id", "run_id"}}` and `:352` passes the same pair as `params`. Double-fire suppression is **exact**, and `job_id` additionally becomes part of the store's owner record (§8.2, §9). |
| D4 | Which channel, which repos? | **Channel:** `C0BPLSPHHDZ` ("glorious-guidance"), which a per-conversation rule adds the link trigger to, with its own override (the interim field-extraction prompt of §15.4). It does no storage — replies live in channel history only, consistent with §15.4. **When that override is updated to register items it must name the same `--state-file` as the cron prompt** (§8.2) — the one setup step with no error path if got wrong. **Repos:** `jiuwenswarm` for v1. Widening is not a migration, since §8.3 makes repository a column; what is unverified for agent-core is its GitCode project id, MR numbering and CI artifact paths. |

Also confirmed: `JIUWENSWARM_DATA_DIR` **is** present, so prompts and scripts
resolve it at runtime rather than hardcoding a path (§8.1). `XDG_STATE_HOME` is
**absent**, so the script's default reaches `~/.local/state/…` through its
fallback. The proposed state path was **written, read back and cleaned up**, so
§8.1's location is tested rather than assumed.

**A methodology note, because this design was briefly built on a wrong answer.**
D1 was first measured by reading `/proc/<pid>/environ`, which shows only the
environment a process was **started** with. It does not show what
`load_dotenv()` adds to `os.environ` at runtime — and subprocesses inherit the
*runtime* environment, not the start-up one. The correct measurement is to have
the harness actually launch a script and print which names it can see. Anything
in this document asserting that a credential is unavailable should be re-checked
that way before it is believed.

### Deferred to v2 — none of these blocks v1

- Whether the no-change heartbeat should be suppressible (§13 recommends
  posting; revisit once the operator has lived with it).
- **The `conversations.history` scan of record (§15.3)** — the largest deferred
  item, and the one that closes v1's coverage gap. Designed in full, including
  its watermark and failure modes; it needs the channel manager to stamp two
  derivable fields onto a `channel_id="slack"` cron envelope. Fixes
  `repository-activity-digest` at the same time.
- The `:x:`-reaction untrack path (§12). Needs the v2 scan to be visible on a
  tick, and needs an answer to what a reaction means on a message carrying
  several items (§4.1). Not needed while `track --unregister` and file editing
  exist.
- Tracking upstream PRs we merely depend on, as well as our own; this would
  change the impact ranking, since "about to break something we depend on"
  outranks everything currently in §13's list.
- Retention and pruning (§10 keeps everything; at this volume it will be a long
  time before that matters).
- Re-surfacing interval N (§13 proposes 7 runs) — a number to tune, not to argue
  about now.
- Whether `check_report_language.py` behaves sensibly on table cells; it was
  written for prose. Check when the first table ships.

## 18. Relationship to `repository-activity-digest`

**Separate skill, separate state, separate cron job — and that skill is left
exactly as it is.** Nothing below is a change to propose to it; its cron is not
to be disturbed. The observations are recorded because they are the reasons this
design departs from it.

- **Different unit of work.** The digest reports a *repository* over a window;
  this reports a *roster of items* through their lifecycles. Their state shapes
  are incompatible: the digest's is a firehose watermark (`last_success_utc` plus
  a 10 000-key `seen` set, **currently at its cap**); this one is a row per item
  with no cap. Sharing the file would let FIFO eviction silently retire tracked
  items.
- **Different failure semantics.** The digest may safely skip a window. This one
  must not lose one.
- **Different report shape.** Trend narrative versus change list.

**Borrow, verbatim:** `check_report_language.py` and the `preferred_language`
resolution rule; and the write discipline (`tempfile` in the target directory
then `Path.replace`) already done correctly at
`fetch_repository_activity.py:119-133`.

**Do not borrow** two things:

- **Its watermark commit point.** The digest writes `last_success_utc` inside the
  fetcher (`:1509-1516`), before the model has composed the report and long
  before Slack has it. Its `SKILL.md` step 9 asks the model to check
  `state.written` — but that check runs *after* the write, so it can report the
  problem and cannot prevent it. A turn dying between fetch and delivery consumes
  its window silently. Acceptable for ambient trend data; not for a roster where
  the lost window may be the only time an item was ever approved. §9 commits
  after delivery instead.
- **Its *relative* state path.** The pattern of stating the path in the prompt is
  right and is followed (§8.1); what is not followed is stating it relatively.
  The anchor's cron prompt names `--state-file memory/repository-activity-….json`,
  resolved against a base invisible in the path itself
  (`fetch_repository_activity.py:91-109`). The live watermark is consequently at
  `workspace/projects/memory/…` while a stale 5.4 MB copy of an old raw payload
  sits at `workspace/memory/…` (mtime 2026-07-30), and an operator looking for
  "the state file" finds the wrong one first. State it absolutely.

## Appendix — verification log

All observations 2026-08-12 unless noted. Read-only; no tracker was mutated.

`gh` appears below because it is what *this investigation* used to read GitHub.
It is **not** what the skill uses — §6.1 chooses `GITHUB_TOKEN` over `gh`
deliberately, and the two must not be confused.

**Merge state** (`gh pr list --author harenome --state open`) — 8 open PRs:
#2724, #2723, #2720, #2718, #2669, #2455, #2377, #2095. All
`mergeStateStatus: BLOCKED`. #2455 alone is `DIRTY` / `CONFLICTING` and carries
the `conflicted` label. Zero reviews on any.

**Label vocabulary** (`gh api repos/openJiuwen-ai/jiuwenswarm/labels`) — includes
`ci-running`, `ci-successful`, `ci-failed`, `check-successful`, `conflicted`,
`merged`, `sync-managed`.

**Timeline** (`gh api …/issues/2455/timeline`) — timestamped `labeled` /
`unlabeled` events from `openjiuwen-ci-bot` and
`openjiuwen-collaboration-bot`, including `conflicted` applied
2026-08-12T07:49:52Z. Confirms CI and conflict state arrive as dated events.

**GitHub Checks** — `statusCheckRollup` on #2724 contains only `license/cla`.

**CI writeback** — `openjiuwen-collaboration-bot` comment prefixed
`<!-- bot2-ci-writeback -->` with `head_sha: ea17f8051e…`, a result table, and
links to `…/jiuwenswarm/ut/4717/unit_test_report.html` and `…/package/dist/4717/…`.

**CI artifact** — that URL returns HTTP 200, 4 493 371 bytes, pytest-html v4.2.0.
Its `data-jsonblob` parses to 4 742 records with `result` and `testId`.
Machine-readable without credentials.

**GitCode API** — `https://api.gitcode.com/api/v5/repos/openJiuwen/jiuwenswarm/pulls`
readable anonymously (HTTP 200). Returns `iid`, `state`, `mergeable`,
`merged_at`, `labels`, `head.sha`, `source_branch`, `html_url`. The
`source_branch` query parameter is **ignored**; filtering must be client-side.
`pulls/<iid>` returns `iid: null` (upstream quirk) — use the requested number.

**Pairing** — matching GitHub head shas against GitCode MRs resolved all 8, each
on a branch named `github-pr-<N>` authored by `openjiuwen-sync`: 2724→!4717,
2723→!4716, 2720→!4715, 2718→!4714, 2669→!4686, 2455→!4578, 2377→!4531,
2095→!4378. The OBS artifact path number equals the MR iid.

**GitCode decision labels** — MR !4717 (ours): `github-mirror`,
`sig/jiuwenswarm`, `openJiuwen-cla/yes`, `ci-successful`, and **no `approved`**.
Merged MRs for comparison: !4794 `approved` + `lgtm-zepinzhang` +
`lgtm-hy592070616`; !4792 `approved` + `lgtm-douran` + `lgtm-alan_cheng`.

**Sync-bot PRs do merge on GitHub** — #2850, #2852, #2854, #2855 all carry
`mergedAt` and `sync-managed`.

**The `url` trigger** — `slack_connect.py`: `:2010-2021` (URL-triggered opt-in, after
group mode), `:2345` (bot messages dropped), `:81` (`_USER_CONTENT_SUBTYPES`),
`:2392-2394` (prompt appended), `:2458-2459` (`slack_trigger` metadata).

**One turn per message, regardless of link count** — `_HTTP_URL_RE` is
`re.compile(r"https?://[^\s<>()|]+")` and the gate is `.search(text)`, a single
match on the whole body: `slack_connect.py:2014` in the current checkout,
`:2177` on the deployed `65b1368dd`, identical code. Confirmed in the field
2026-08-12 16:44 UTC in `C0BPLSPHHDZ` — a two-link message produced one dispatch,
two `fetch_webpage` calls, and a reply covering both items, despite a prompt
written in the singular.

**Live channel config** (read 2026-08-12) — the link trigger is enabled for four
channels including `C0BPLSPHHDZ`, and two of them carry a prompt of their own:
`C0BN2F6UDDH` and `C0BPLSPHHDZ`. The `C0BPLSPHHDZ` override requests eight named
fields one per line (Tracker, Repository, Number, Title, Author, State, Created,
Last activity), permits `unknown` for any of them, forbids analysis or review,
and asks for a single line when the link is neither a pull request nor an issue.

**History tool unavailable on cron** — `interface_deep.py:395-407` requires
`slack_channel_id` and `slack_history_digest_allowed`; `:6150` gates registration
on it; `gateway/cron/scheduler.py:1021-1031` builds the cron envelope with
`metadata={"cron": {...}}` only.

**Block Kit** — `slack_connect.py:3193-3198` (`auto` renders any Markdown table);
`slack_blocks.py:49-53` (50 blocks, 3 000 section chars, 100 rows, 20 columns,
10 000 table chars).

**portalocker precedent** — `gateway/cron/store.py:13`, `:140-153`
(`cron_jobs.json.lock`); the companion lock file is present on disk.

**JSONL ledger precedent** — `ai-news-monitor/scripts/ledger.py`: `home()` at
`:295-315` resolves `--home` > `AI_NEWS_HOME` > `XDG_STATE_HOME` >
`~/.local/state/ai-news-monitor` — the same explicit-then-XDG order the house
pattern states, in a different spelling — and falls back to reading a legacy
store rather than starting a fresh ledger that would re-report everything;
`ledger_path()` / `state_path()` at `:329-334`; `reject_path_in_skill_dir()` at
`:220-238` refuses working files inside the skill directory, with the incident
that motivated it recorded in the docstring. Flags in use across the installed
skills: `--state-file`, `--raw-output`, `--output`, `--out`, `--input`,
`--output-format`, `--profile`, `--home`.

**The anchor's path lives in its prompt, not its script** — the cron job
description for `repository-activity-digest` carries
`--state-file memory/repository-activity-openJiuwen-ai-jiuwenswarm.json`
explicitly (`~/.jiuwenswarm/agent/home/cron_jobs.json`).

**Credentials (D1, D2)** — measured by launching a probe script through the
harness itself (`jiuwenswarm chat --session probe-env-delta-1 --mode agent`) and
printing **names and lengths only, never values**. Visible to a script launched
by a skill: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `GITHUB_TOKEN` (40 characters,
a classic PAT), `TRELLO_API_KEY`, `API_KEY`, `JIUWENSWARM_DATA_DIR`, `HOME`.
Absent: `GH_TOKEN`, `JIUWENSWARM_HOME`, `XDG_STATE_HOME`.

**Superseded measurement** — an earlier reading of `/proc/<pid>/environ` reported
the Slack and GitHub variables as absent. That file shows only a process's
**start-up** environment and misses everything `load_dotenv()` adds to
`os.environ` at runtime; subprocesses inherit the runtime environment. The
`/proc` reading was wrong and the probe above supersedes it. Note the Slack
tokens are recorded here as *reachable*; v1 not using them is a scope decision
(§15), not a consequence of this measurement.

**v2 envelope enrichment (§15.3)** — `gateway/cron/scheduler.py:54` sets
`channel_id = (job.targets or CronTargetChannel.TUI.value)…`, so a `targets:
slack` job already satisfies the first test in
`_filter_slack_history_request_metadata` (`interface_deep.py:395-407`). The two
remaining fields are `slack_channel_id` and `slack_history_digest_allowed`; the
latter is computed by the connector at `slack_connect.py:2453-2456` as
`"*" in history_digest_channel_ids or channel_id in history_digest_channel_ids`.
The same gate is why a CLI turn cannot read history either (§15.2).

**Store path** — the probe wrote, read back and deleted a file under
`…/agent/workspace/state/skills/<name>/`, confirming the §8.1 location is
creatable and writable by the service account.

**Cron metadata (D3)** — `gateway/cron/scheduler.py:766` builds
`metadata={"cron": {"job_id": job.id, "run_id": ev.run_id}}`; `:352` passes the
same pair as `params`.

**Store location** — `JIUWENSWARM_DATA_DIR` is the runtime's own resolution root
(`jiuwenswarm/common/utils.py:401-409`; 20 references across the package).
`agent/workspace/state/` does not exist yet (checked). Sandbox allowed-root
fallback `[workspace, project_root, cwd, *skill_roots]` is stated verbatim in
agent-core `fix/sandbox-skill-roots-v2` (`b01280e5`).

**Backup coverage** — `~/.config/borg-backup/jiuwenswarm.conf:21`:
`SOURCES="/home/jiuwenswarm/.jiuwenswarm /home/jiuwenswarm/.cache/jiuwenswarm"`.
The exclude file lists only `pycache`, `agent/.checkpoint`,
`workspace/memory/memory.db`, `.agent_teams/team.db`, `**/*.db-wal`,
`**/*.db-shm`, `**/*.lock`, `**/.lock`, `**/__pycache__`, `**/*.pyc`. So
`agent/workspace/state/` is backed up, `~/.local/state` is not, and a
`*.jsonl.lock` sidecar is excluded — which is correct.

**Anchor relative-base** — `fetch_repository_activity.py:76-88`
(`JIUWENSWARM_DATA_DIR`, else `~/.jiuwenswarm`), `:91-99` (base is
`<data dir>/agent/workspace/projects`), `:102-109` (relative paths resolved
against it).

**Anchor state** — live watermark at
`workspace/projects/memory/repository-activity-openJiuwen-ai-jiuwenswarm.json`:
`{last_success_utc: 2026-08-12T06:00:07Z, seen: [10 000 keys]}` — at its cap.
Orphan 5.4 MB raw payload at `workspace/memory/…` (mtime 2026-07-30). Watermark
written at `fetch_repository_activity.py:1509-1516`, before report composition
and delivery.
