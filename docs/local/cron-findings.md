# Cron findings

Collected while building a report skill driven by `cron_jobs.json`, 2026-08-13.
Each item is something the cron path does that a caller has to work around, with
the evidence and a proposed disposition. None is a defect the product would
notice on its own — they surface only when a scheduled job has to *produce
something for a channel* rather than run silently.

Anchors are against `local/deployed` (`1a74ee462`) unless stated.

---

## 1 · A scheduled run cannot use the trusted Slack history tool

`_filter_slack_history_request_metadata` (`server/runtime/agent_adapter/interface_deep.py:395-407`)
fails closed unless the request metadata carries both `slack_channel_id` and
`slack_history_digest_allowed`. Only the Slack connector writes those
(`slack_connect.py:2455-2470`), and it writes them for inbound Slack events.

The cron scheduler builds its envelope with `metadata={"cron": {"job_id": …,
"run_id": …}}` (`gateway/cron/scheduler.py:766`) and nothing else. So on a
scheduled run the gate returns `{}` and the tool is absent.

**This is not a policy decision about cron.** The gate exists so an untrusted
caller cannot claim to be a channel; the connector is the only thing positioned
to vouch. Cron simply has no path through it. Evidence that the policy already
permits it: this deployment runs `history_digest_channel_ids: ["*"]`, so every
channel is allowed — it is the plumbing that is missing, not the permission.

**The gap is small.** The cron envelope already carries `channel_id="slack"`
(`scheduler.py:54`, `channel_id = (job.targets or …)`), so it *already passes* the
gate's first test. Only the two fields are missing, and both are derivable at
dispatch: the job knows its target channel, and the allowance is a pure function
of connector config (`"*" in history_digest_channel_ids or channel_id in …`,
`slack_connect.py:2453-2456`).

**Proposed:** have the channel manager enrich a `channel_id="slack"` envelope with
those two fields on its way through, using the check the connector already
applies. No new trust model, no relaxed gate. `repository-activity-digest`
benefits identically.

**Also affects the CLI.** `jiuwenswarm chat` is not a Slack turn either, so a
skill invoked there cannot read channel history. It fails as an *empty result*,
not an error — indistinguishable from an empty channel.

---

## 2 · `description` is capped at 500 characters, which caps the prompt

`CRON_JOB_DESCRIPTION_MAX_LENGTH = 500` (`gateway/cron/models.py:118`). A job whose
description exceeds it is rejected by `CronJob.from_dict`, and `store.py:206-211`
swallows the exception — *"Ignore invalid entries to keep system robust"* — so the
job silently does not load. The only symptom is `[Cron] loaded N job(s)` counting
one fewer than the file contains.

The limit is **a UI form-field constraint, not an execution one**. The comment
says so (`models.py:116-117`): *"名称/描述最大长度（前后端保持一致，见
CronTaskDrawer.tsx 同名常量）… 描述对齐产品确认的 500"* — mirrored from the cron
drawer's textarea, agreed with product. Introduced in `c9a2ce83b` inside a bulk
fix commit.

**Why it matters here:** a cron job's `description` *is* the prompt. A skill whose
instructions run to 50 lines cannot be scheduled without rewriting them to fit,
which is prompt engineering imposed by an unrelated frontend constant.

**Proposed:** raise the backend limit, or drop it and keep the frontend's own.
Note the two are already independent constants in different languages, so they
are not actually kept consistent by anything but convention.

**Currently worked around locally** by patching the constant in the deployed venv.
That patch is reverted by any rebuild, deliberately.

---

## 3 · The "still running" placeholder is unconfigurable and unlocalised

When the push falls due before the agent has produced a result, the scheduler
posts (`scheduler.py:1382-1386`):

```python
placeholder = (
    f"{job.name} is running. Results will be posted when ready "
    f"(scheduled_at={state.push_at_iso})."
)
```

Three problems, in increasing order of how much they matter:

- **Not templated.** One f-string, one call site, no config key. The only
  per-job influence is `job.name`, which is interpolated. A deployment that wants
  different wording, or none, cannot have it.
- **Hardcoded English**, with no `preferred_language` path — the same class as
  other user-facing strings fixed recently. Under a Chinese-preferring
  deployment it is an English sentence in otherwise Chinese output.
- **Leaks `scheduled_at` as an ISO timestamp with offset** into a human-facing
  channel message.

**Caution for anyone changing the wording:** it is load-bearing elsewhere.
`CRON_LEADER_PLACEHOLDER_MARKERS` (`common/cron_team_completion.py:8-19`) detects
this text by substring to decide whether a team leader has actually finished. A
reword must update both, or completion detection silently breaks.

**Proposed:** a `placeholder_text` job field defaulting to today's string, and a
language path for the default. Match the marker constant to whatever the default
becomes.

---

## 4 · `wake_offset_seconds` is the placeholder's off switch, and is not described that way

`wake_dt = push_dt - timedelta(seconds=max(0, job.wake_offset_seconds))`
(`scheduler.py:741, 936, 1351`). The agent wakes that many seconds before the push
is due.

With the default `0`, wake and push coincide, so the result can never be ready
and **the placeholder always fires**. Give the job enough offset to finish and
the placeholder is skipped entirely, because `_on_push` finds a result.

That makes it the per-job control for "announce that this is running" versus
"only post the result" — which is exactly the distinction an operator wants
between a long background task and a quick one. It reads as a scheduling detail
rather than as that control.

**Proposed:** document it in that role. No code change needed.

---

## 5 · A scheduled agent cannot confirm its own delivery

The agent's reply is delivered *after* its turn ends. So any instruction of the
form "do X only after your reply has gone out" is unsatisfiable on the cron path:
the agent either does X before replying, or never.

This is not a cron defect so much as a property callers must design around, and
it is easy to write a prompt that assumes otherwise — the manual and scheduled
forms of the same instruction need opposite orderings. Observed concretely: a
report skill told to commit its watermark after posting never committed, and
re-reported the same items on every tick until the ordering was inverted.

**Two shapes that work**, worth recording because the choice is not obvious:

- **Commit before replying.** Simple, one job. If delivery then fails, that run's
  changes are marked reported and never resurface — bounded, and loud, since a
  failed cron delivery raises and notifies.
- **Commit the previous run's pending at the start of the next run.** A new run
  starting means the previous delivery either succeeded or failed loudly. One
  job, no second watermark, and the loss window shrinks from permanent to one
  cycle. Correct by construction; needs the caller to keep a pending receipt.

A third shape — one job that produces to disk and commits, another that delivers
what changed — also works, but needs its own "have I delivered this yet" state,
which is the thing the second shape avoids.

---

## 6 · What the cron path does supply

Recorded because it was not obvious and had to be established:

- **`cron.job_id` and `cron.run_id`** are both in metadata
  (`scheduler.py:766`, and as `params` at `:352`). So exact double-fire
  suppression is available to a caller, not merely best-effort.
- **`targets` becomes `channel_id`** verbatim (`scheduler.py:54`), which is why the
  envelope already satisfies the history gate's first test.
- **`post_as_root: true`** clears the thread anchor (`slack_connect.py:3243-3266`),
  so a report and its threaded-detail half arrive as two top-level messages
  rather than a message and a reply.
- **The delivery channel comes from `session_id`**, not from `targets`:
  `_extract_delivery` splits it and takes `parts[2]` (`slack_connect.py:3258-3265`).
  A job posting to a given Slack channel therefore needs
  `session_id: slack_<team>_<channel>_<anything>`, which is not documented
  anywhere and is easy to get wrong.

---

## 7 · There is no concurrency policy, and self-overlap is unbounded

Every due job becomes a fire-and-forget asyncio task (`scheduler.py:1106`):

```python
task = asyncio.create_task(_run_agent(), name=f"cron-run-{job.id}")
self._run_tasks[run_id] = task
```

No semaphore, no queue, no priority, no serialisation, and no ceiling on how many
runs may be in flight. `is_running()` (`:318`) refers to the *scheduler loop*, not
to a job. The scheduler is a hand-rolled asyncio loop rather than APScheduler, so
that library's `max_instances`, `coalesce` and `misfire_grace_time` are not
available either.

**Two distinct situations, and only one of them is anyone else's convention to
solve:**

**Different jobs due on the same tick.** Both run concurrently. This is the
operator's responsibility in essentially every scheduler — classic cron, systemd
timers, APScheduler and Kubernetes CronJob all leave it alone. systemd comes
closest to helping and does so by *smearing start times apart*
(`RandomizedDelaySec=`, `AccuracySec=`) rather than by coordinating. So the
idiomatic fix here is the same: schedule them onto different ticks.

Observed concretely: a two-minute job and a six-minute job collide every sixth
minute. Both read and write the same skill store. Each caller's own file lock
keeps the store consistent, but two runs of a reporting skill produce two pending
receipts, and whichever commits second overwrites the first's watermark. Harmless
when both rendered from near-identical state; not harmless in general.

**The same job overlapping itself is the real gap.** `_runs` is keyed by `run_id`,
which embeds the fire timestamp, so a run that outlives its own interval does not
block the next tick — it accumulates. Every other scheduler names a policy for
exactly this:

| System | Same job overlapping |
|---|---|
| systemd timer | prevented; the unit is the lock, an active `.service` will not re-trigger |
| classic cron | not prevented, hence the `flock` idiom in crontabs |
| APScheduler | `max_instances` (default 1); a second run is dropped with a warning |
| Quartz | `@DisallowConcurrentExecution` |
| Kubernetes CronJob | `concurrencyPolicy: Allow / Forbid / Replace` |

Nothing equivalent exists here. A job slower than its interval piles up silently
and indefinitely. At two-minute ticks with twenty-second runs this is nowhere
near, but a daily job that grows past twenty-four hours would accumulate with no
warning and no bound.

**Proposed:** a per-job `concurrency` field with `allow` (today's behaviour, and
the default so nothing changes) and `forbid` (skip the tick and log it). `forbid`
is the value almost every deployment wants, and it is a few lines given
`_run_tasks` already tracks live tasks per `run_id` — the check is whether any
live task exists for this `job_id`. Cross-job collision needs no product change:
it is scheduling, and belongs in whatever writes the jobs.

**Note for anyone measuring this:** the two-minute job in these tests carried
`wake_offset_seconds: 60`, so its agent wakes a minute before its push. Overlap
is therefore wider than the cron expressions alone suggest — a job's occupancy is
`offset + runtime`, not `runtime`.

---

## 8 · Editing a live job's timing can leave it unscheduled

Changing `wake_offset_seconds` on a job with a run in flight, then restarting,
left the job silently idle. The reload found the in-flight run's `wake_dt` now in
the past and declined it as crash recovery:

```
[Cron] reload skip wake+push (crash recovery, wake_dt in past) job=… run_id=…
```

which is correct — a stale run should not fire late. But nothing then scheduled
the *next* occurrence, so the job stopped entirely. Two ticks were missed with no
error; a second restart, by which time no live run state remained, recovered it.

The symptom an operator sees is "cron just stopped", with the only evidence a
single INFO line whose wording suggests recovery succeeded.

**Proposed:** after declining a stale run, fall through to scheduling the job's
next occurrence rather than returning. The decline and the reschedule are
independent decisions and are currently coupled.

---

## 9 · Every prompt-created job lands in the wrong timezone

Added 2026-08-27, anchored against `local/deployed` (`9c3c5ef63`).

All eleven jobs in this deployment's store are `Europe/Paris`. Both jobs created
by asking the agent for one, in the same session, came out `Asia/Shanghai` — a
six-hour error in summer, silently applied.

The default is hardcoded in two places, and the tool schema advertises it to the
model as well:

```
cron_tools.py:373   timezone=str(normalized.get("timezone") or "Asia/Shanghai")…
controller.py:185   timezone = str(params.get("timezone") or "Asia/Shanghai")…
controller.py:555   "description": "Time zone (IANA), e.g. Asia/Shanghai"
controller.py:556   "default": "Asia/Shanghai"
```

So the model does not merely fall through to the fallback — it is *told* what the
default is, and both the example and the default name the same zone. A request
that does not state a timezone gets that zone whichever path it takes.

**Visible but skimmable.** The confirmation does print `Timezone: Asia/Shanghai`,
so nothing is concealed. It sits in a list of six fields the reader is scanning to
check the schedule, which is exactly where a wrong-but-plausible value survives.
Neither of the two jobs was caught this way; both were caught by reading the store.

**Why it is not an upstream defect.** The default is presumably right for the
users it was written for. It becomes wrong only in a deployment whose operator
is somewhere else, and there is no configuration that says where that is — the
same shape as items 1 and 3, where a reasonable upstream choice has no local
override.

**Not yet decided.** Three dispositions, cheapest first:

- **Config key**, e.g. `cron.default_timezone`, read at both sites with the
  current literal as its own default. No behaviour change for anyone who does not
  set it, and it survives a rebase better than a changed constant.
- **Patch the two literals.** One line each, but it is a local divergence in a
  file that upstream touches, and the schema `default`/`description` would drift
  from the code unless changed too.
- **Say it in the prompt.** Costs nothing and works today, but it is policy in
  prose guarding a value the runtime knows — it fails whenever someone asks for a
  cron without the boilerplate.

The first is preferred on the reasoning that the runtime already knows every
other delivery detail; the operator's timezone is the one it has no way to learn.

**Impact so far: none.** Both affected jobs were test jobs, both deleted the same
day. The eleven real jobs predate this and are all correct.

---

## 10 · The timezone default is upstream's, and there is no key to override it

Recorded 2026-08-28, extending item 9. Item 9 said the default is "hardcoded" and
left open whether the fix is local or upstream. It is now measured:

```
jiuwenswarm/agents/harness/common/tools/cron/cron_tools.py   develop 1, ours 1
jiuwenswarm/gateway/cron/controller.py                       develop 4, ours 4
```

Byte-identical counts on both sides. **We carry no patch**, so there is nothing to
bundle and no local change to undo. `Asia/Shanghai` is upstream's own default,
and a reasonable one for the users it was written for.

**So this is neither our defect nor a prompt problem.** It is a setting whose
correct value is deployment-specific and which has no key. Fixing it properly
means adding one upstream — `cron.default_timezone`, read at both call sites with
the current literal as its own default, so nobody who does not set it sees a
change.

That is new work rather than a rebundle candidate, and it belongs with two
neighbours of the same shape:

- `models.defaults[].stream_first_chunk_timeout` / `stream_idle_timeout` — right
  for upstream, absent here until set by hand
- `message_summary_offloader_config.protected_tool_names` — needs `read_pdf`
  locally, and the template already knows it

All three are values upstream chose sensibly and no operator elsewhere can
change without editing a literal or a list a merge will never touch. A single
small upstream bundle arguing "a setting whose correct value is
deployment-specific should be a key" is a better shape than three unrelated
local patches. **Not started.**
