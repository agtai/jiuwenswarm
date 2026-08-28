# ai-news-monitor: why it fails, and what to do about it

Written 2026-08-26, before the machine migration. The work described here was
deliberately deferred until after the move. Nothing in this document has been
applied.

## Symptom

The `ai-news-monitor` cron reporting into Slack channel `C0BQECEQ7GU` fails in
one of two ways:

**A — tool-loop bailout.** The run aborts with

```
[153001] context execution execution error, reason: reasoning/tool loop
unresolved after repeated compaction: the model repeated identical tool loops
through 3 compaction(s) (processor=ReasoningToolLoopCompactProcessor,
rule=bailout_threshold, threshold=3)
```

The channel keeps the streamed narration, frozen at the abort, and **on builds
before 2026-08-27 the cron reported that narration as a successful result**; see
*Re-measured 2026-08-27* below. Its tail is the loop verbatim — the same sentence
seven times:

```
I have strong in-window candidates. Now verifying primary sources (Step 4).
```

**B — gateway abandonment.** The gateway gives up after 60 minutes, cancels the
task, and posts a timeout notice. The task may already have finished.

## The failure is older than the model switch

The default model changed at the service restart on 2026-08-25 16:42:33 UTC.
This job has been failing intermittently **since 2026-08-16**, under the previous
model: 08-16 (three times), 08-17 (twice), 08-18, 08-20, plus softer failures
through 08-25.

What the switch changed is the rate. The figures first recorded here — about one
run in eight before, three of three after — came from counting the runs that
*announced* a failure, which on the builds of the time was a fraction of the runs
that failed. The **post-switch** figure is corrected in *Re-measured 2026-08-27*
below. The pre-switch period has **not** been recounted, so the size of the
before-and-after gap is now unknown in both directions, and no comparison should
be drawn from the two figures as they stand.

What survives is the claim this section was written to make, which rests on dated
failures rather than on rates: the job was already failing on 2026-08-16, nine
days before the switch. Reverting the model would therefore not fix it. Whether
reverting would *improve* it is exactly the question the missing pre-switch count
would answer.

## Mechanism: per-token generation cost, not web latency

Measured directly against the endpoint on 2026-08-26.

Model, same 9k-token prompt, varying output length:

| output tokens | wall clock |
|---|---|
| 8 | 3.2 s |
| 400 | 8.9 s |
| 1500 | 33.5 s |

So roughly **20 ms per generated token**, plus prefill of about 0.5 s per 1000
prompt tokens.

Web I/O, measured the same day:

| call | wall clock |
|---|---|
| DuckDuckGo search | 0.2 s |
| Bing search | 0.2 s |
| page fetch (822 KB) | 0.3 s |

A failing run made 39 LLM calls over 57.7 minutes, median 98 seconds between
consecutive calls, with roughly 81 tool calls in total. **All of the web I/O in
that run costs about 22 seconds.** The wall clock is essentially all model.

This matters for choosing a fix: making the searches concurrent would save
seconds out of an hour. The cost is the number of turns and the length of each
generation, not the network.

Prefill scales with context, and it has its own hard budget:
`stream_first_chunk_timeout` defaults to 300 s and is unset in this deployment,
so a turn whose context has grown large enough to spend five minutes in prefill
is killed before it emits a token, then retried twice with the identical
request. See `slack-stream-timeouts-and-retry.md` -- same root-cause family,
different symptom, and the mitigations below do not address it. In particular,
mitigation 2 raises the *job's* timeout, which does nothing about a budget
enforced per model call.

## Data loss, and why the state file lies

The 10:30 run on 2026-08-26 **succeeded and was killed two minutes short**. It
wrote its digest, link-checked it, and recorded five items to the ledger at
11:28:15; the gateway cancelled it at 11:30:30.

The five items are in
`agent/workspace/state/skills/ai-news-monitor/C0BQECEQ7GU/ledger.jsonl` with
`recorded_at=2026-08-26T11:28`, and `state.json` reads `"runs": 25`. Because
they are in the ledger they count as seen, so they will never be reported.
The channel shows a timeout; the state shows success.

Any similar timeout loses whatever the run had already recorded. Reading the
state file alone will not reveal it.

## Re-measured 2026-08-27: the true rate, and why it looked healthy

Twelve consecutive ticks were counted from the scheduler's own
`[Cron] push_to_targets` records, 2026-08-25 13:45 to 2026-08-27 13:45. **Two
produced a digest.** Six hit the mode A bailout; three hit the mode B gateway
timeout; one is the 08-26 10:30 run recorded above, which finished and was
cancelled.

The two that worked are 08-26 19:45 (10 ledger items) and 08-26 22:45 (7 items).
Every other run committed nothing.

A digest-sized push is roughly 7–11 KB. **A push of 2.0–3.2 KB is an aborted run**
— that band held for every one of the six bailouts and is the cheapest way to
classify a tick without opening its session.

### Why the job looked healthy

On builds before the 2026-08-27 restart an abort came back over the wire as
`e2a.complete` carrying the partial narration, so the scheduler recorded
`status=succeeded` (`gateway/cron/scheduler.py:1069`) and posted the narration
into the channel. Four consecutive aborted runs on 08-27 appeared in
`#knowledgeable-king` as ordinary cron output. Their text is the loop:

```
The window is tight (~11.5h since last run at 2026-08-26 23:01 UTC).
Let me continue the sweep across the remaining beats.
[the same sentence, three more times]
```

The section above says *the channel shows a timeout; the state shows success.*
This is its worse sibling: **the channel shows success, and nothing happened at
all.** Anyone auditing this job by reading the channel will conclude it is
working.

The 13:45 run on 08-27 is the first on the new build, which returned `e2a.error`
and so recorded `status=failed` with the reason
(`scheduler.py:1098-1102`). Every earlier abort tracebacks to the previous venv,
the 13:45 one to the current venv, and the agent server restarted between them at
12:20:37. **The correlation is measured; the causal claim is not** — n=1 on the
new build, and the adapter branch that chooses complete-vs-error was not found.
Confirming it on a later tick is the cheapest open question here.

### Each failure widens the next run's window

`state.json` advances `last_run` only at commit, which an aborted run never
reaches — SKILL.md:931 says so directly: *"`last_run`, which this call has not
advanced yet"*. As of 2026-08-27 it still reads:

```json
{"last_run": "2026-08-26T23:01:34+00:00", "runs": 27, "last_window": "1d"}
```

So every tick since derives a wider window from a frozen mark — about 14.5 hours
by 13:30 and growing. **The job degrades on its own**, independently of the model
or the timeout, and this is the only failure here that compounds. It is also the
cheapest to stop: cap the window, or advance the mark on failure.

### Compaction is triggered by repetition, not context pressure

The three compactions in the failed run:

```
13:44:09  messages=50 tokens=63409   -> 36
13:54:51  messages=66 tokens=87856   -> 52
14:07:58  messages=82 tokens=106024  -> 68   -> bailout
```

The endpoint's `max_model_len` is 1048576, so the largest of these is about 10%
of the budget. Every record reads `compacted consecutive identical
reasoning_tools rounds`. **Context growth is a consequence of the loop, not its
cause**, so raising a context limit would not help.

Effective thresholds, logged at every agent init: `bailout_threshold: 3`,
`consecutive_threshold: 3`, `tool_args_bailout_threshold: 2`.

### Near-misses: two compactions is already fatal

Across the log window, seven sessions reached three compactions and every one
aborted; four reached exactly one and recovered. **No session stopped at two.**
The 19:45 success compacted once; the 22:45 success never compacted. So the
useful signal is the *second* compaction, not the third.

### How far a failed run gets

The 13:45 run's directory holds only `run.json` (13:37:48). No `candidates.json`,
no `retrieved-urls.txt`, no `digest.md`. It never reached Step 3 — 29 minutes of
Step 2 sweep, then the abort. A successful run reaches Step 7 and writes its
ledger items. Nothing is checkpointed, so an abort discards the whole run rather
than the current step.

### Incidental: the ledger script path is wrong twice per run

At 13:38:00 and 13:38:25 the model invoked
`…/state/skills/ai-news-monitor/scripts/ledger.py`. There are two roots and only
one has `scripts/`:

```
workspace/skills/ai-news-monitor/scripts/   <- exists
workspace/state/skills/ai-news-monitor/     <- no scripts/
```

Two turns wasted on the confusion SKILL.md warns about at line 178, which means
the warning as written is not preventing it.

## What was ruled out

Each of these was tested and refuted, so nobody needs to re-derive them:

- **Multimodality.** The skill contains no image handling. The modality probe
  never fired inside any run of this job.
- **Strict tool schemas.** This job uses no strict-schema tool and requests no
  structured output. The `extra_forbidden` failures seen around the same time
  belong to a different skill in a different session.
- **The stale skill symlink.** The cron reads
  `agent/workspace/skills/ai-news-monitor`, which is current. See the separate
  note below — the symlink is a real problem, but not this one.
- **Context window.** The endpoint reports `max_model_len: 1048576`. No
  context-length error appears anywhere. Context size costs latency, not
  truncation.

## The abort mechanism is not upstream's current code

Found after the rest of this note was written, and it reorders everything below.

`ReasoningToolLoopCompactProcessor` -- the component whose bailout ends these runs
-- **is not present on `upstream/develop`**. It was added upstream in July, then
removed on 2026-08-12 by `94e10cb6`, *fix(rail): Rectify model anomaly detection
rail*:

```
-574  openjiuwen/core/context_engine/processor/compressor/
        reasoning_tool_loop_compact_processor.py
-241  openjiuwen/harness/rails/llm_retry_rail.py
+652  openjiuwen/harness/rails/model_anomaly_detection_rail.py
+340  tests/unit_tests/harness/test_tool_loop_compact.py
```

Our deployed agent-core is dated the same day and does **not** carry that commit,
so the deployment still runs the retired processor. On `develop` the class survives
only in documentation; the implementation is gone.

The first failures here are dated 2026-08-16, four days after upstream removed it.

The replacement is a single anomaly-detection rail in place of a hard bailout plus
a retry rail, which matches the direction upstream states in its own open feature
request for loop detection and recovery: recoverable rather than hard-killed.

**So the first thing to try is not in this document's mitigation list: establish
whether adopting `94e10cb6` removes the failure mode outright.** Two caveats. It is
652 lines of new rail against a fork carrying 217 commits of divergence, so it is an
integration rather than a cherry-pick. And upstream's loop-detection feature request
remains open, so upstream does not consider the problem closed even with the new
rail -- the recovery-by-steering design it describes was merged to an enterprise
branch, not to `develop`.

## Mitigations

Ordered by durability rather than by effort. Read the section above first: if
adopting `94e10cb6` resolves this, most of what follows is unnecessary.

### 1. Pin the channel to the previous model (immediate, reversible)

A scope naming this channel and pinning `agent.model_name` to the earlier model
restores the pre-switch failure rate for this one job while everything else stays
on the new default.
The earlier model is already a second `models.defaults` entry, so no new
endpoint configuration is needed.

This is a stopgap. The intent is to move fully to the new model, so treat it as
buying time, not as a fix.

### 2. Raise the job's timeout (immediate, partial)

`timeout_seconds` is 3600 on this job. The 10:30 run proves the work completes;
it needed about 62 minutes. Raising it to 7200 converts mode B into a slow
success. It does nothing for mode A.

Consider widening the schedule at the same time. The narration shows the model
thrashing when the window is thin — "The window is tight (last ~12h)" appears
seven times in one run — so a longer interval may reduce the looping as well as
the frequency of failures.

### 3. Batch tool calls within a turn (cheap, prompt-only)

`parallel_tool_calls` is already `True` in `AbilityManager`, backed by
`asyncio.gather`. The observed ratio is about 2.1 tool calls per turn, so the
model is searching, thinking, searching, thinking. Eight searches issued in one
turn cost one prefill instead of eight.

This reduces turns without reducing coverage, and needs no code change.

### 4. Move retrieval out of the turn loop (the durable fix)

The two scheduled jobs that never fail this way — `pr-tracker` and
`repository-activity-digest` — run a deterministic script and hand its output to
the model. `ai-news-monitor` instead makes the model the fetch orchestrator,
paying a full context prefill for every retrieval decision.

Inverting that means a script does the searching and fetching, and the model
sees the assembled corpus once and does what only it can do: judge relevance,
deduplicate, and write.

**This increases coverage rather than reducing it.** At 0.1–0.3 s per fetch a
script can afford breadth the turn loop cannot. Capping the number of items to
save tokens would be the wrong fix — it discards the information the job exists
to find. The cost is per turn, not per item.

After this change the job stops being sensitive to per-token latency, which
makes the model choice a preference again rather than a constraint.

### 5. Reasoning and effort control (blocked on the endpoint)

`OpenAIModelClient` carries a rule table that merges provider-specific
`extra_body` fields into a request, selected by a predicate on the model name:

```python
@dataclass(frozen=True)
class ModelParamRule:
    name: str
    predicate: Callable[[str], bool]
    extra_body_fields: Mapping[str, object]
```

Exactly one rule ships, matching a different vendor's models. The model in use
here matches nothing, so nothing is injected. `_MODEL_PARAM_RULES` is a class
attribute, so adding a rule is small.

Scoping, if the endpoint ever exposes a reasoning or effort parameter:

- **Per channel or per cron**: available today with no code change. A second
  `models.defaults` entry under an alias, plus a scope whose `agent.model_name`
  names it. Same endpoint, same model, different client configuration.
- **Per request**: needs a rule. `extra_body` is applied per request, but there
  is no per-call knob.

The endpoint does not currently advertise such a parameter, and probes returned
no reasoning field, so none of this is testable yet.

## Two adjacent problems, worth fixing separately

**The skill is not in version control.** `agent/workspace/skills/ai-news-monitor`
holds the live skill — SKILL.md has grown to about 65 KB — and none of it is in
`local_skills/`, which carries only `pr-tracker`. Only a test file was ever
committed. The workspace is backed up, so the content survives, but there is no
history, no diff and no revert. An `assets/digest-template.md.bak-presync-*`
file suggests a sync was started and not finished.

**A stale symlink points at a pre-migration path.**
`agent/workspace/projects/ai-news-monitor` is a symlink to
`/home/ubuntu/code/skills/ai-news-monitor/`, another account's home. That copy
was last modified 2026-07-31 and is roughly half the size of the live one. It is
not on the cron's path today, but anything resolving the skill through
`projects/` would silently get the old version — and on a new machine that path
will not exist at all.

## The skill in git is current — this needs hardening, not a resync

Checked 2026-08-28 by extracting `local_skills/ai-news-monitor` at
`local/deployed` and diffing it against the live workspace copy. **Three
differences, all runtime artefacts**: a `.bak-presync` file under `assets/`, and
the `runs/` and `store/` directories the skill writes into. No skill content
differs.

So the failure rate recorded above is not a stale-version problem, and re-syncing
the skill would change nothing. The two digests in twelve ticks are what the
current text produces.

What that leaves, in the order they compound:

1. **The frozen `last_run`** widens every subsequent window, so each tick is
   harder than the last. Cheapest to stop and the only failure here that worsens
   on its own.
2. **The tool-repetition loop** that triggers the compaction bailout. The root
   behaviour; needs the sweep step reworked rather than tuned.
3. **No checkpointing**, so an abort discards the whole run rather than the step.

None is started.
