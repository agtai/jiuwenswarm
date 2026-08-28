# A streamed reply is posted twice when the model speaks before a tool call

Found 2026-08-27 while testing an unrelated feature. **Deferred: to be addressed
after the machine migration.** Recorded now because the cause is understood and
the evidence will not survive log rotation.

Anchors are into the running tree,
`jiuwenswarm/gateway/channel_manager/im_platforms/slack/slack_connect.py`.

## Symptom

One user turn produces two bot messages carrying the same answer. The second is
a superset of the first: identical text, plus the paragraphs the model wrote
after the first was posted. A reader sees the answer, then sees it again.

Observed in `#misty-mall` on a turn that created a cron job. Three turns the same
day in another channel produced one message each, which is what scoped it.

## What the log says, in order

```
13:55:40  streaming opened   mode=stream opening_chars=210
13:56:36  streaming closed   edits=5 failed=0
13:56:36  WARN  the finished reply does not continue what was streamed:
                streamed_chars=569 final_chars=696
13:56:37  delivered text     mode=post            <- the second message
```

The turns that behaved end differently:

```
streaming finished: appends=16 failed=0 tail_chars=493 one_message=yes
```

`one_message=yes` is the good outcome. The duplicating turn never reaches it.

## The mismatch is a prefix, and the prefix is the preamble

Read back from Slack, the two messages align byte for byte once 210 characters
are removed from the front of the streamed one — exactly the `opening_chars=210`
the stream opened with. `final.startswith(streamed[210:])` holds;
`final.startswith(streamed)` does not.

The model emitted a short paragraph, called a tool, then wrote the real answer.
The tool call is logged between the two.

**Why that breaks the test.** The delta stream accumulates every assistant text
block in the turn — `_extract_delta_text` (`:7633`) skips only
`source_chunk_type == "llm_reasoning"`, and `_stream_delta` (`:7180`) never
resets at a tool call. The terminal `answer` chunk carries the final assistant
message alone. So `surface.sent_text` holds preamble + answer while the terminal
event holds answer, and a `startswith` comparison between them cannot succeed.

`_streamed_remainder`'s own docstring states the assumption: *"they… normally
agree, because the terminal event repeats the whole reply."* True for a turn with
one text block; false for a turn that says anything before calling a tool.

This half is **inferred** rather than captured — from the 210-character match,
the byte alignment, the delta filter admitting non-reasoning text, and the
terminal event's source. No delta payload was captured for this turn.

## The double post is deliberate, and its premise is sound

`_streamed_remainder` (`:7136`) finds no continuation and returns `None`
(`:7158`). `_finish_streamed_reply` (`:6814`) then takes the branch at `:6862`,
whose comment reads:

> The finished answer is not a continuation of what was streamed -- a runtime
> that rewrote its reply rather than extending it. Nothing can be appended that
> would make the message right, so it is taken out of streaming state and the
> answer is posted whole below it.

That premise is correct: nothing appended can fix the message. The conclusion is
what leaves the duplicate, because posting the answer below does not retract the
stale partial above it.

**There is no in-place-rewrite rung to reach.** `_recover_streamed_reply`
(`:6918`, called at `:6894`) is parameterised by `remainder=` — it appends what
is left, so it does not fit a case whose defining feature is that no remainder
exists. Replacing the streamed message wholesale with the final text is a path
the connector does not currently have, not one it has and skips. Anyone reading
this later should not expect a one-line reroute.

The branch returns `False` at `:6876`; `send()` (`:3869`) sees it, and because
`root_update_ts` was cleared at `:3838`, `_post_root` (`:3940`) posts a fresh
message.

## Recurring, and not all the same shape

Ten occurrences of the warning in retained logs between 2026-08-21 and
2026-08-27, across five channels, excluding a test fixture. One fired twenty
minutes before the observed incident.

**Two of the ten have `final_chars < streamed_chars`.** Those cannot be a
missing-preamble case and have not been diagnosed. Do not assume one cause
covers all ten.

## Where it lives

Ours. `_streamed_remainder`, `_finish_streamed_reply` and
`_SlackStreamingSurface` arrived in `06f299748` and `46103c3df`, both authored
locally; the upstream Slack connector has no streaming surface at all. The
runtime-side asymmetry — deltas spanning the turn, the terminal event carrying
one block — is not ours, but the connector is what turns it into two messages,
and the connector is what assumed otherwise.

Not configuration: `channels.slack.enable_streaming` is global with no
per-channel key, and both the duplicating and the well-behaved channels streamed.

## Not established

- Whether the `edit` streaming mode diverges the same way. Only `stream` was traced.
- What the two shrinking cases are.
- Whether a captured delta payload would confirm the inferred half.

## Disposition

Deferred until after the migration. Two directions, neither costed:

- **Give the `None` branch a rewrite rung** — replace the streamed message with
  the final text via `chat.update`, leaving one message. The observed payload was
  695 characters, far under the edit ceiling, but the ceiling still has to be
  handled for longer replies, and a rewritten message loses its streaming state.
- **Fix the comparison instead** — reset the delta accumulator at a tool call so
  `sent_text` and the terminal event describe the same span. Narrower, and it
  addresses the cause rather than the consequence, but it assumes the tool-call
  boundary is observable at that point, which has not been checked.

See also [[slack-stream-timeouts-and-retry]] for the other failure mode of the
same streaming surface; they are independent.
