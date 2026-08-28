# Slack stream timeouts and the retry window nobody can see

Written 2026-08-27, before the machine migration. Nothing here has been applied.
The subject is a single behaviour: a model call can stall for ten to fifteen
minutes with nothing new on screen, and the connector has no way of knowing why.

Measured on the `2026-08-26-full-v22` build -- jiuwenswarm
`integration/v22-pending` (`90a1e0025`), agent-core `local/deployed`
(`80a53799`). Code claims cite `file:line` against those two trees; upstream
claims cite `upstream/develop`.

## Symptom

A turn in a Slack channel died with

```
[181001] model call failed, reason: LLM stream timeout: stream frame timeout:
stage=first_chunk, timeout=300.0s, chunk_count=0, first_chunk_elapsed=300.00s,
total_elapsed=300.00s, model=deepseek-v4-flash-0731
```

`chunk_count=0` is the whole diagnosis. The stream produced no parsed chunk at
all, so nothing was generated and nothing was thrown away: the five minutes went
into prefill. That distinguishes it from every failure mode where the model
produced something unusable.

## Where the 300 seconds comes from, and why it is a default nobody chose

`Model.invoke` reads two budgets off the client config before it starts pulling
chunks (`openjiuwen/core/foundation/llm/model.py:174-175`) and applies them per
`__anext__` according to whether anything has arrived yet
(`model.py:202-203`):

```python
stage = "first_chunk" if chunk_count == 0 else "idle_chunk"
next_timeout = first_chunk_timeout if chunk_count == 0 else idle_timeout
```

`_resolve_stream_timeout` (`model.py:90-92`) is a `getattr` against
`model_client_config` and nothing more, so the values are whatever the schema
defaults to. They are declared in
`openjiuwen/core/foundation/llm/schema/config.py`:

| key | default | line |
| --- | --- | --- |
| `stream_first_chunk_timeout` | `300.0` | 57-61 |
| `stream_idle_timeout` | `60.0` | 62-66 |
| `timeout` (HTTP request) | `360.0` | 50-56 |

Neither stream key appears anywhere in the deployment's config, so both defaults
apply. `timeout` **is** set, to 1800 -- and that is the shape of the problem.
The schema itself says the HTTP timeout is "kept >= `stream_first_chunk_timeout`
so the transport layer never times out before the application-level stream
timeout" (`config.py:53-55`). Raising the transport budget to half an hour
without touching the application budget leaves the 300 s cut-off in charge, and
it is the one that fires. The operator's intent -- allow slow calls -- was
expressed against the key that was not deciding.

Both keys accept `None`, which disables the check entirely. That is a worse
answer than a larger number: it converts a slow call into an unbounded one.

## What the retry rail does, and what it costs

`LLMRetryRail` hooks `on_model_exception`
(`openjiuwen/harness/rails/llm_retry_rail.py:124-131`) and retries when the
exception text carries either of two markers (`:17-21`):

```python
_STREAM_TIMEOUT_MARKERS = (
    "LLM stream timeout",
    "stream frame timeout",
)
```

The rail is on by default (`openjiuwen/harness/factory.py:227`, `:402`) with
`max_retries=2` and backoff `(0.5, 1.0, 2.0)` (`llm_retry_rail.py:24`, `:44`,
`:73`). Retry is requested through
`AgentCallbackContext.request_retry` (`openjiuwen/core/single_agent/rail/base.py:477-490`),
which re-runs the wrapped model call -- the same messages, the same tools, the
same everything. Nothing about the request changes between attempts, so a stall
caused by the size of the prompt is reproduced exactly.

**The ceiling is three attempts, not two.** The counter is compared before it is
incremented (`llm_retry_rail.py:216-223`), so the first failure retries as
`(1/2)`, the second as `(2/2)`, and the third propagates. At the default budget
that is `3 x 300 s + 1.5 s` of backoff -- **up to 15 minutes**, not the ten a
two-attempt reading suggests. The observed incident spanned about ten minutes of
wall clock, consistent with two attempts rather than three.

Two knobs that look like they would help and do not:

- `max_retries` on the model client config (`config.py:68`) is transport-level.
  Its own description says so: *"Whole-call retries are handled by
  LLMRetryRail."*
- Adopting upstream's `94e10cb6` -- the commit the `ai-news-monitor` note
  recommends trying first -- does **not** change this. It deletes
  `llm_retry_rail.py` and folds its behaviour into
  `openjiuwen/harness/rails/model_anomaly_detection_rail.py`, which carries the
  identical markers, the identical `max_retries=2` and the identical backoff
  tuple (`:29-35`, `:124`, `:325`). The stall window survives the migration
  unchanged. Worth knowing before the two problems get treated as one.

## What the reader actually sees, which is less bad than assumed

Both of these were checked against a real failed turn rather than reasoned from
the code, and one of them refutes a standing assumption.

**The status card is not lost.** The retry happens inside the model layer,
below the connector; the connector holds the card's message ts throughout and
keeps editing the same message. Observed across the retry: the card's last edit
moved from 13:16:10 to 13:26:22, and its content advanced from
`1m 51s - 3 tools` to `2m 17s - 4 tools finished`. Nothing was orphaned and
nothing was duplicated.

**Terminal failure is surfaced.** When the retries were exhausted the card
finalised as `Turn failed - thought for 2m 17s - 4 tools finished - [181001] …`
and the error was additionally posted as its own message. An earlier assumption
that the card would sit on `Working` forever was **wrong** -- `_activity_status`
replaces the stem with `_ACTIVITY_TITLE_FAILED` once the record closes
(`slack_connect.py:861`, `:6018-6019`, `:6031`), and closing is what a propagated error
does.

**But the ten minutes are invisible while they pass.** The card's duration is
not wall clock. `_thinking_summary` reports `record.reasoning_seconds()`
(`slack_connect.py:5722-5739`), which accumulates only the stretches during
which reasoning was streaming (`:3117-3122`, opened and closed at `:3100-3102`, `:3104-3115`).
A first-chunk stall produces no `CHAT_REASONING` event, so the counter does not
move: 26 seconds of displayed elapsed across ten minutes of real time. The card
is honest about what it measures and silent about what it does not.

## The gap: the event exists and has no consumer

`LLM_CALL_ERROR` is fired on every stream timeout, before the error is raised
(`model.py:230-235`):

```python
await trigger(
    LLMCallEvents.LLM_CALL_ERROR,
    model_name=effective_model_name,
    model_provider=model_provider,
    is_stream=True,
    error=exc)
```

It goes into openjiuwen's callback framework. The connector reads a different
thing entirely: gateway `EventType` values from
`jiuwenswarm/common/schema/message.py:220-255` -- `CHAT_TOOL_CALL`,
`CHAT_TOOL_RESULT`, `CHAT_REASONING`, `CHAT_ERROR`, `TODO_UPDATED`,
`CONTEXT_USAGE`, `CHAT_PROCESSING_STATUS` and a dozen more. **Grep finds zero
references to `LLM_CALL_ERROR` anywhere in jiuwenswarm**, in code, tests or
docs.

So "subscribe the connector to it" is not a subscription change. There is no
gateway event to subscribe to; something has to bridge the openjiuwen callback
into a gateway `EventType` first, and no such bridge exists for any
`LLMCallEvents` member. This is the same shape as the known subagent-events
gap -- an event emitted faithfully into a stream nobody drains.

The mechanism for consuming one is not exotic and is already demonstrated in
this tree: `tests/system_tests/test_system_prompt_live_capture.py:148-157`
registers a callback on `Runner.callback_framework` for `LLMCallEvents.LLM_INPUT`
and unregisters it after. What is missing is a place to put the result, not a
way to obtain it.

## Streaming mode, and the case nobody has run

The connector's reply surface matters here because a retry is a restart of the
generation, and what a restart does to a half-written message depends on how
that message is being written.

Three corrections to the assumptions this section started from:

- **The key is set.** `channels.slack.enable_streaming` is `true` in the
  deployment. It is not absent, and absence would not mean streaming:
  `resolve_streaming_mode(None)` returns `STREAMING_MODE_DEFAULT`, which is
  `STREAMING_OFF` (`slack_connect.py:314-326`, `:1207-1208`), and the config
  dataclass default is `False` (`:3192`). `resolve_streaming_mode({})` does
  return `'stream'`, but only through the unreadable-value fallback at
  `:1221-1227`, which logs a warning first. It says nothing about this
  deployment.
- **`stream` is a ladder, not a setting.** `_new_stream` (`:7208-7253`) asks for
  `chat.startStream` only where Slack will take it -- a threaded reply, to a
  channel whose recipient ids are known -- and falls back to the `edit` preview
  otherwise. So the streamed surface applies to threaded replies, not to every
  reply.
- **A mid-stream retry is reachable in code**, not merely conceivable. The rail
  matches `stage=idle_chunk` timeouts with the same markers, and the default
  idle budget is 60 s; the repetition detector (`llm_retry_rail.py:115-122`)
  fires strictly after chunks have arrived. Either path re-issues the call once
  appends have already been sent.

What is genuinely untested is the consequence. On the streamed surface the
connector would be holding an open stream while the model layer restarts the
generation from scratch. Whether the second attempt's chunks append to the first
attempt's text, and whether the message is closed at all, is unknown. That last
part is what makes it worth testing rather than assuming: `chat.stopStream` is
the call that delivers the message (`slack_connect.py:2456`, `:2703`), so a
stream left open is a reply that was never delivered -- a strictly worse outcome
than the failure this note describes, which at least ends with an error on
screen.

## Why it bites now

Same root-cause family as the `ai-news-monitor` note: the current default model
is slow at large contexts, and prefill scales with the context. The failing turn
was paginating fourteen days of a two-hundred-message channel. A turn in the
same period needing one tool call and a small context completed, taking 6m 07s.
Neither number is a defect on its own; the defect is that a fixed 300 s budget
was chosen for neither of them.

## Recommendations

Measured facts are above this line; everything below is a proposal.

1. **Set `stream_first_chunk_timeout` explicitly**, to a value that reflects
   real prefill at the context sizes actually reached. This is a one-line config
   change and it is the only item here that needs no code. Set a number rather
   than `None` -- an unbounded first-chunk wait trades a visible failure for an
   invisible hang. The transport `timeout` is already 1800 and so will not
   constrain the choice, but the schema's `>=` relationship should be kept
   deliberately rather than by luck.

2. **Bridge `LLM_CALL_ERROR` to a gateway event and show a retry state on the
   status card.** The card already re-renders on every event it receives, so the
   display cost is small once the event arrives. Two decisions are worth making
   first: whether the bridge is specific to this event or general to
   `LLMCallEvents`, and whether the card shows the attempt count -- `retrying
   (1/2)` is honest, and a spinner that never advances is what the reader has
   today.

3. **Test the mid-stream retry before relying on it.** The idle-timeout path
   makes it reachable without waiting for a rare coincidence: a stream that goes
   quiet for 60 s mid-generation exercises exactly the case. Check whether the
   text duplicates and, more importantly, whether the message is closed at all.

4. **Consider making the elapsed figure on the card wall clock, or adding it
   alongside.** The reasoning-only figure is defensible and is documented as
   deliberate, but it means the one number on screen during a stall is the one
   number that does not move. This is the smallest change that makes a stall
   visible, and it does not depend on item 2.
