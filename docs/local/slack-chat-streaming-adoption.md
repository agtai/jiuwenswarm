# Adopting Slack's chat streaming API in the Slack connector

Status: investigation and proposal, since revised by measurement. No connector
code is changed by this document and nothing was posted to a shared channel;
the three streaming methods were later exercised against the live API in a probe
channel, and everything that came back is tagged [PROBE] and outranks the
reading it replaced.

Three of its conclusions were overturned that way — §8.4, §9.4 and §6.3.1 — and
the reading each replaced had looked settled. Two of them are worth stating as a
lesson about this API rather than as errata:

- **A reference page marking an argument Optional does not make it optional**,
  and its errors table is not exhaustive (§8.4). `thread_ts` is required and
  `invalid_thread_ts` is undocumented.
- **A field named for a format reads that format**, whatever the surrounding
  connector writes elsewhere (§9.4). Sending mrkdwn into `markdown_text` was a
  defect in already-written code, caught by a probe rather than by review or by
  tests — the tests asserted the wrong dialect confidently.

The remaining unmeasured items in §9 should be treated as unknown rather than as
probably-fine. Every one that has been measured so far has come back different
from the reading.

Four questions were asked -- three at the outset and one after the rest of this
document was written -- and all four have answers. Three of them overturn the
premise they were asked under:

| # | question | answer |
| --- | --- | --- |
| Q1 | replace, or add behind a toggle? | **Replace**, and do not put the choice in the config file at all. `enable_streaming` stays the boolean it always was; which path a given reply takes is decided per reply against what Slack will accept for it. §4.1. |
| Q2 | can the activity card and the answer become one message? | **It can be built and must not be.** `task_update` is real and the rendering was never the problem. A stream lasts ~5 minutes [PROBE] and the card has to outlive the work, so unification is abandoned rather than deferred. §6.3.1. |
| Q3 | is Block Kit accepted only at `stopStream`? | **No.** A `blocks` chunk is accepted at `appendStream`, in position. The premise that charts would move to the end is wrong. |
| Q4 | does [Agent Sessions](https://docs.slack.dev/ai/agent-sessions/) supersede this? | **No — it sits above it.** `chat.startStream` is one of the two documented ways to drive a session, streaming is not deprecated, and the SDK cannot call sessions at all yet. §11. |

## 0. Which trees the facts come from

Three sources, and they are kept apart throughout because two of them disagree
in one place (§7.3).

- **[CONNECTOR]** — the deployed connector,
  `/home/jiuwenswarm/venvs/current/lib/python3.12/site-packages/jiuwenswarm/gateway/channel_manager/im_platforms/slack/slack_connect.py`,
  7629 lines, with `slack_blocks.py` at 2081 beside it. Not the repository's
  default checkout, which differs substantially in this file.
- **[SDK]** — `slack_sdk` 3.43.0 as installed in that same tree. Method
  signatures and model classes read directly; one offline probe run against a
  stubbed `api_call` to see the wire payload the SDK builds. No network.
- **[DOCS]** — `docs.slack.dev`, fetched 2026-08-21. Quoted where it matters.
- **[PROBE]** — `chat.startStream` called against the live API on 2026-08-21,
  in a probe channel, with curl. Added after the rest of the document was
  written. **It outranks the other three wherever they disagree**, and in §8.3
  it disagrees with [DOCS] twice over. Everything tagged this way is a
  measurement; everything else is a reading.

§11 was added after the rest and reads the same three trees; where its two
disagree, §11.8 says so rather than picking one.

## 1. What the API is

### 1.1 The three methods [SDK]

```python
async def chat_startStream(
    self, *, channel: str, thread_ts: str,
    markdown_text: Optional[str] = None,
    recipient_team_id: Optional[str] = None,
    recipient_user_id: Optional[str] = None,
    chunks: Optional[Sequence[Union[Dict, Chunk]]] = None,
    task_display_mode: Optional[str] = None,  # timeline, plan
    icon_emoji=None, icon_url=None, username=None, **kwargs,
) -> AsyncSlackResponse
```

```python
async def chat_appendStream(
    self, *, channel: str, ts: str,
    markdown_text: Optional[str] = None,
    chunks: Optional[Sequence[Union[Dict, Chunk]]] = None, **kwargs,
) -> AsyncSlackResponse
```

```python
async def chat_stopStream(
    self, *, channel: str, ts: str,
    markdown_text: Optional[str] = None,
    blocks: Optional[Union[str, Sequence[Union[Dict, Block]]]] = None,
    metadata: Optional[Union[Dict, Metadata]] = None,
    chunks: Optional[Sequence[Union[Dict, Chunk]]] = None, **kwargs,
) -> AsyncSlackResponse
```

Note what the signatures do **not** carry: `blocks` appears on `stopStream`
alone. That is the shape that produced the operator's reading, and taken by
itself the reading is correct — but `chunks` is on all three, and a chunk can
carry blocks. §5 works this through.

`AsyncChatStream` (`slack_sdk/web/async_chat_stream.py`) wraps the three behind
`append()`/`stop()` with a `buffer_size` (default 256 characters) that decides
when a buffered append is actually flushed, and lazily calls `startStream` on
the first flush. It is a thin convenience; it is not required, and this
connector already owns the debounce logic the buffer duplicates.

### 1.2 The four chunk types [SDK] [DOCS]

`slack_sdk/models/messages/chunk.py` defines exactly four, and the docs
document the same four identically on all three method pages:

| type | fields | purpose |
| --- | --- | --- |
| `markdown_text` | `text` | the answer body |
| `plan_update` | `title` | retitle the plan |
| `task_update` | `id`, `title`, `status`, `details`, `output`, `sources` | one task's progress |
| `blocks` | `blocks` | an array of Block Kit blocks, in position |

> "The `chunks` parameter can include markdown text chunk objects, task update
> chunk objects, plan update chunks, or blocks chunks."
> — [chat.appendStream](https://docs.slack.dev/reference/methods/chat.appendStream) [DOCS]

The SDK's own docstrings for `append()` and `stop()` say "Chunks can be markdown
text, plan, or task update chunks" and omit blocks. The docs and the model class
both contradict that docstring; treat it as an SDK documentation bug, not as a
constraint.

### 1.3 What the SDK actually puts on the wire [SDK]

`_parse_web_class_objects` (`slack_sdk/web/internal_utils.py:190`) converts
`blocks`, `user_auth_blocks`, `attachments`, `chunks` and `metadata` from model
objects to dicts, and leaves raw dicts alone. Probed offline against a stubbed
`api_call`, `chat_appendStream` with a mixed chunk list produces:

```json
{
 "channel": "C1", "ts": "1.1",
 "chunks": [
  {"text": "hi", "type": "markdown_text"},
  {"blocks": [{"type": "data_visualization", "title": "t", "chart": {}}],
   "type": "blocks"},
  {"id": "a", "status": "in_progress", "title": "T", "type": "task_update"}
 ]
}
```

Two things follow. Chunks are serialised correctly, so the SDK is usable as-is.
And a raw dict block of a type the SDK's model does not know — here
`data_visualization` — passes through a blocks chunk untouched rather than being
dropped by `Block.parse`. That matters because the connector builds its blocks
as raw dicts and two of its types are not in the SDK model at all (§5.3).

## 2. What the connector does today [CONNECTOR]

`_SlackMessageSurface` (line 1759) is post-then-edit:

- `open(text)` → `_post_text(...)` → `chat_postMessage`, returns the `ts`.
- `write(handle, text, sequence)` → `_wait_for_stream_slot`, then `_post_text(update_ts=handle)` → `chat_update`. On failure it latches `failed` and keeps `error`.
- `close(handle, text, sequence)` → nothing:

  > "The closing edit is the delivery, so it obeys `send()`'s raise contract and
  > is made there. Nothing to do here."

The `text` passed to `write` is not a delta. `_stream_delta` accumulates into
`stream.text` and calls `session.replace(self._stream_snapshot(stream.text))` —
the whole answer so far, re-rendered, every time. The protocol is
**replace**-shaped end to end. This is the single most important fact for §4.

Throttles: `_STREAM_DEBOUNCE_MS = 1000` and
`_STREAM_MIN_UPDATE_INTERVAL_SECONDS = 1.0`, keyed by channel, both justified in
comment by `chat.update` drawing on the same budget as `chat.postMessage`.

`_stream_snapshot` is explicit that the preview is text-only:

> "Text only, deliberately. A stream is a message rewritten roughly once a
> second, and a table built a row at a time is worse to watch than the same rows
> arriving as plain text ... the terminal event rewrites this message in full
> through `send()`, and that rewrite is where the blocks land."

So **no block reaches the channel mid-answer today**. A chart from a `vega-lite`
fence, a `data_table` from a Markdown table — none of them appear until the turn
ends. §5.1 turns on this.

Ceilings: `_MAX_SLACK_TEXT_LENGTH = 38000` for a post,
`_MAX_SLACK_UPDATE_TEXT_LENGTH = 4000` for an edit, the latter because
`chat.update` rejects the whole call with `msg_too_long` past 4,000 characters.
Every streamed write is bounded by 4,000, and `send()` sizes the reply's first
chunk to 4,000 whenever it is rewriting a streamed message.

## 3. Scopes: nothing to change

All three method pages list one scope and only one [DOCS]:

> "Scopes — Bot token: `chat:write`"

The connector already holds `chat:write`; it posts and edits with it on every
turn. **No app-configuration change is required, and the `missing_scope`
failures the token already shows on `conversations.info` and `conversations.list`
are unrelated** — those are `channels:read`-family scopes, and streaming does not
touch that family.

This is the largest single de-risking fact in the assessment. The usual reason
to hold a new API behind a permanent toggle — that it may turn out to be
unavailable to this app — does not apply.

Two adjacent findings, both stated with their uncertainty:

- **Gating.** No page found — method references, the
  [7 Oct 2025 changelog](https://docs.slack.dev/changelog/2025/10/7/chat-streaming/),
  the messaging guide, or Slack's own agent article — carries any "beta",
  "Enterprise only", "AI apps program" or "marketplace approval" language. The
  changelog frames it as general: "Slack apps can now stream in their responses
  to the end user using three new API methods." This is the **absence** of
  gating language, not a positive statement of general availability. It is
  strong but not conclusive.
- **`enterprise_is_restricted`** appears in the errors table of all three
  methods — "The method cannot be called from an Enterprise". This is shared
  boilerplate across most `chat.*` methods, not a streaming-specific
  restriction.

## 4. Q1 — replace, or toggle?

### 4.1 The toggle already exists

`enable_streaming: bool = False` (line 2162). The streamed preview is opt-in and
off by default. So the choice is not "one delivery path or two". It is:

- `send()`'s post-and-chunk path — used by cron pushes, questions, file
  uploads, digests, errors and every non-streamed turn. **It stays, whatever is
  decided.**
- the streamed-preview path — already optional, already separable.

Adopting streaming changes the second. The question is whether the operator
picks between the two ways of writing a preview, and the answer this arrived at
— after building it the other way first — is **no**.

#### The tri-state, and why it was withdrawn

The flag was widened to `off` / `edit` / `stream` on the reasoning above: a third
value preserves the current path as a rollback, and a rollback value nobody runs
is dead code with a deletion date rather than a live second path. That was built,
shipped to a test workspace, and then reverted before anything reached a
downstream config. The reasoning that removed it is stronger than the reasoning
that added it:

- **The choice depends on something a config file cannot see.** `stream` needs a
  thread to reply into (§8.4). Whether a reply has one is decided per reply, from
  the inbound event. An operator setting `stream` is not choosing a delivery
  path; they are choosing it *for the replies that can take it* and silently
  choosing nothing for the rest — which is exactly the defect that shipped
  (§4.1.1).
- **The only motive to pick `edit` is to dodge the five-minute expiry** (§9.1) —
  a rough edge. A knob whose purpose is routing around a rough edge is the wrong
  shape; the edge is what should be fixed.
- **Nobody asked for it.** It was invented while building the feature. Nothing is
  upstreamed, so shipping it and collapsing it later would cost downstream users
  two migrations for a key they never needed to touch.
- **If `stream` turns out worse than `edit`, that is one line here**, in a
  release, rather than a config change every deployment has to make.

Accepted deliberately: an operator who finds streaming rough has no middle
setting, only off. If a middle setting turns out to be what people want, that is
the signal that `stream` should not yet be what `true` means — and the fix is to
change what `true` means, not to make operators configure around it.

The three names survive as an **internal** concept, because the ladder needs
them. They are not a config surface.

#### 4.1.1 The ladder, and the regression that produced it

A reply that cannot be streamed falls to `edit`, not to `off`. This was learned
the hard way: the first version marked such a reply's stream failed, which left
the answer posted whole at the end of the turn. Turning `stream` on therefore
**removed** the progressive preview from every DM answered at the top of the
conversation and every channel with `reply_in_thread: false` — a mode meant to
show more showing less, in exactly the places the config file gives no hint
about.

So: `stream` where Slack will take it, `edit` where it will not, `off` only when
asked for. The fallback is scoped to *a stream that never opened* — refused up
front by `_cannot_stream`, or whose opening call failed — because in both cases
nothing is on screen yet and the swap is invisible. A stream that has already
appended is never swapped: a message in streaming state refuses `chat.update`
outright (§9.2), and the close and its recovery ladder deliver the whole answer
anyway.

That reframing matters for the divergence risk the operator raises. The defects
where one path behaved differently from another — the subtype check reachable on
the DM path but not the channel path — arose between two paths that were **both
live**, both receiving traffic, both expected to work. Two internal modes chosen
per reply *are* both live, and that is the cost being accepted here: the ladder
is worth it because the alternative measured worse.

### 4.2 Recommendation

**Replace, in two phases, with `enable_streaming` left as the boolean it has
always been.**

- Phase 1: stream the answer. The activity card stays a separate message.
- ~~Phase 2: unification (§6), only after Phase 1 has run and after a test
  workspace has settled §9.~~ **Abandoned. The card must outlive the work and a
  stream lasts about five minutes; §6.3.1 has the measurement.** What is left of
  the plan is Phase 1 alone.

`edit` is kept, and not as a rollback lever. It is the rung a reply lands on
when a stream cannot be opened for it (§4.1.1), which is a permanent condition
rather than a transitional one: a DM answered at the top of a conversation will
never have a thread to stream into.

That is a real cost and it is worth stating rather than smoothing over. The two
modes are not behaviourally equivalent and cannot be tested as if they were.
`edit` clamps at 4,000 characters and splits; `stream` does not (§7.1). `edit`
renders blocks only at the end; `stream` renders them in position. Every
downstream assertion about chunk counts, message counts and block placement
forks, and both rungs are live — which is the divergence this connector has
already been bitten by, now permanent rather than dated.

It is accepted because the measured alternative is worse: withdrawing the
preview from every DM to keep one code path (§4.1.1). The mitigation is that the
rung is chosen in exactly one place, `_new_stream`, on conditions that are
themselves measured — so "which path did this reply take" has one answer and one
log line, rather than being spread across the delivery code.

The reason to stage rather than land it whole was a new API against a live
deployment with an unknown server-side expiry (§9.1) and turns that run for
minutes. That reasoning held up better than intended: the expiry is real, it is
about five minutes, and it turned out to disqualify the second phase outright
rather than merely to need measuring first (§6.3.1). Phase 1 meets the same
expiry on the answer path, where a stream that dies mid-turn costs a frozen
preview and nothing else — the answer is still delivered in full when the turn
ends.

### 4.3 Does `_SlackMessageSurface` absorb it?

Mostly. `open`/`write`/`close` map onto `start`/`append`/`stop` at the level of
names. Three places leak, and they are worth naming precisely because two of
them are contained and one is not.

**Leak 1 — the protocol is replace-shaped, append is delta-shaped.** `write()`
receives the full accumulated snapshot. A streaming surface must send only what
is new, so it must diff against what it has already sent — which is only sound
if the snapshot is a stable prefix of the next snapshot. `_stream_snapshot` is
**not** prefix-stable: it runs `_normalize_slack_mrkdwn` (which rewrites
`**bold**` to `*bold*` only once the closing marker arrives, so an already-sent
prefix becomes wrong), it strips markers that can straddle deltas, and it clamps
to 4,000 with a truncation suffix.

This is contained, and the fix is an improvement. `_stream_snapshot` is a
`SlackChannel` method the surface does not own; making the rendering a property
of the surface lets the streaming surface use the raw accumulated text, which
*is* a stable prefix because it is pure concatenation of deltas. It also drops
the normalisation entirely if `markdown_text` accepts real Markdown — see §9.4,
which is a test-workspace question.

**Leak 2 — who performs the terminal delivery.** `close()` is a no-op precisely
because `send()` owns the closing rewrite and its raise contract. Under
streaming, `stop()` is mandatory: it is what takes the message out of streaming
state, and it is the natural place for the trailing blocks. So the closing
delivery moves into the surface, and `send()` must stop issuing a `chat.update`
against a streamed `ts`. This inverts a contract that is currently documented in
two docstrings and relied on by `_post_root`. Contained, but it is the change
that most needs review: `send()`'s obligation to raise on a failed delivery has
to survive the move intact, or a failed answer goes quiet again — the exact
regression `SlackDeliveryError` was introduced to close.

**Leak 3 — `send()` must know which surface it closed.** `first_limit =
_MAX_SLACK_UPDATE_TEXT_LENGTH if root_update_ts else 0` exists because an edit
takes 4,000 and a post takes 38,000. A stream takes 12,000 per append with no
documented total (§7.1), so the splitting decision genuinely differs by mode.
This one does not hide behind the surface abstraction and should not be made to.

Verdict: **the toggle is close to a surface swap, but not free.** Two contained
changes and one honest fork in `send()`.

## 5. Q3 — Block Kit across the stages

### 5.1 Blocks are accepted at append, in position

The operator's reading is wrong, in the favourable direction. From all three
method pages, identically [DOCS]:

> "The `blocks` chunk is used for passing an array of blocks within a message."
> ... "At most 50 blocks can be sent in one blocks array. If more than 50 blocks
> are sent via chunks, any blocks over the limit will be dropped and a warning
> will be emitted via the API."

And `chat.stopStream`'s separate top-level `blocks` argument is explicitly the
*trailing* one:

> "A list of blocks that will be rendered at the bottom of the finalized
> message."
> ... "Note that any blocks in the blocks array will be rendered after anything
> passed via chunks or markdown_text when the stream is completed."

So there are two distinct block channels with different semantics:

| channel | when | where it renders | budget |
| --- | --- | --- | --- |
| `blocks` chunk via `chunks=` | start, append or stop | **in position**, interleaved with the streamed text | 50 |
| `blocks=` argument | stop only | **at the bottom**, after everything | 50 |

Total 100 — "you can have 50 blocks sent via the `chunks` parameter and 50
blocks sent via the `chat.stopStream` API method's `blocks` array, for 100
blocks total." The connector's `MAX_BLOCKS_PER_MESSAGE = 50` already matches the
chunk budget, so no budget shrinks.

### 5.2 What it costs — nothing; it is a gain

The question was framed as "a chart currently visible while the answer streams
would appear only at the end". That is backwards. **No chart is visible while
the answer streams today**, by deliberate design (§2). The streamed preview is
text-only and every block lands in the closing rewrite.

So the comparison is:

| | today | with streaming |
| --- | --- | --- |
| chart from a `vega-lite`/`mermaid` fence | at the end only | **in position, as it is produced** |
| `table` / `data_table` | at the end only | in position |
| activity card `plan` | separate message | see §6 |
| harness-error `rich_text_preformatted` | inside a task card's `details`, on the card message | unchanged, or a `task_update` `details` (§6) |

Streaming is a strict improvement here. The design rule that follows is simple
and should be written into the code: **in-body structure goes in `blocks`
chunks; the `blocks=` argument at stop is reserved for things that genuinely
belong last**, such as feedback buttons. Putting body content in the stop
argument would silently move it to the bottom.

### 5.3 Which blocks actually stream

Two of the connector's block types are not in the SDK's model and do not appear
in the docs' blocks-chunk example: `data_visualization` (`slack_blocks.py:913`)
and `data_table` (`slack_blocks.py:1956`). `slack_sdk` 3.43.0 knows `table` but
neither of those, and passes both through a chunk untouched (§1.3).

**Both stream** [PROBE]. `data_visualization` is accepted in a `blocks` chunk on
`appendStream` and on `stopStream` alike, so a chart renders in the position it
was written in. An earlier report that charts were rejected was a malformed
payload in the probe itself — the real block nests `categories` inside
`axis_config` — and is withdrawn.

**One block type does not stream: `file`.** It faults both streaming methods
with `internal_error`, reproducibly, while posting normally through
`chat.postMessage` [PROBE]. Note the shape of that failure: `internal_error` is
a fault rather than a clean rejection, and it is not in
`_BLOCK_REJECTION_ERRORS`, so the close would latch instead of falling back.
This connector builds no `file` blocks, so it is unreachable — but the streaming
close admits `internal_error` to a rejection set of its own for that reason,
kept apart from the posting path's so a transient fault there does not start
costing renderings.

The general mitigation stands: `_BLOCK_REJECTION_ERRORS` retries without blocks
on `invalid_blocks`, `invalid_blocks_format` and `msg_blocks_too_long`, and the
streamed close does the same with its chunks — dropping the rendering and
keeping the text, because the caller supplies the same content unrendered.

### 5.4 The composition model changes

Today, blocks **replace** a message's text — `_root_blocks_for` says so
directly, and `render_blocks` converts the whole message into an ordered block
list where prose becomes `section` blocks and tables become `table`/`data_table`
blocks. Under streaming, prose is `markdown_text` and only the structured pieces
are blocks.

That is a cleaner model and it deletes the awkward `_section_blocks_for`
fallback ("a body with no rendering of its own has to be given one before a card
can sit above it"). But it is a rewrite of the composition layer, not a swap.
The good news is that `render_blocks` already segments the message in document
order (`_segment` returns an ordered mix of prose, `_Table` and `_Blocks`), so a
variant that returns an ordered list of *chunks* rather than a flat block list
is a modest refactor of a function that already does the hard part.

## 6. Q2 — unifying the card with the answer

### 6.1 It is real

`task_update` exists in the SDK and in the docs, and one stream can carry both
the activity display and the answer. From `chat.startStream` [DOCS]:

> "`task_display_mode` — Specifies how tasks are displayed in the message.
> `timeline` task updates render as individual task cards interleaved with
> streamed text. `plan` task updates render together in a plan block. Default:
> timeline"

and Slack's own worked example puts plan chunks, task chunks and answer text on
one stream before a single `stopStream`.

`task_display_mode="plan"` is the mode that matches what this connector already
renders: one plan, sections inside it, the answer beneath.

### 6.2 What it buys

The 03:18 ordering defect becomes structurally impossible. Today the card and
the answer are two messages tracked separately — `_SlackActivityRecord.message_ts`
and `_SlackStream.surface.opened_ts` — with no ordering relationship, which is
how a "Turn finished" card landed between chunk 1 and chunk 2. One message with
ordered appends has no such gap.

It also removes, or at least shrinks, several things that exist only to manage
two messages:

- `_post_activity_card_later` and `activity_card_delay_seconds`. The delay
  exists so "a turn that finishes before it elapses leaves nothing behind at
  all". Under unification the message exists from the first delta regardless, so
  a fast turn simply emits no task chunks — the same outcome, without a timer.
- `activity_card_min_edit_seconds` and `next_edit_at`. These ration `chat.update`
  calls. `appendStream` is a cheaper tier (§7.2) and sends only the delta.
- `remember_written` / `subagent_card_status`, which exist to detect that the
  message on screen contradicts the record. An append-only stream cannot
  contradict itself the same way.

And §7.1's larger ceiling attacks the same defect from the other side: the
answer that split into four messages did so because of the 4,000-character edit
limit. At 12,000 per append with no documented total, most answers stop
splitting at all.

### 6.3 What blocks it, and it is not the rendering

**The interrupt.** `_remember_activity_alias` and the `closed`-but-kept record
exist for one reason: "A turn resumed after an interrupt is a new request on the
wire but the same request to the person who asked, and it rebinds to this card
instead of posting a second one beside it."

A stream cannot be reopened. `chat.appendStream` returns `stopped_by_user` —
"The streaming message was stopped by the user and no further appends are
accepted" — and `chat.stopStream` returns `message_not_in_streaming_state` once
finished. So a resumed turn either:

1. gets a **new** message, losing the rebinding the alias machinery provides; or
2. requires the stream to be left **open** across the whole time a human takes
   to read a question and click a button — which is exactly the interval an
   undocumented server-side expiry (§9.1) is most likely to cross.

Neither is acceptable without knowing the expiry. **This is the reason
unification is Phase 2 and not Phase 1.**

#### 6.3.1 The expiry is now known, and it does not merely block this — it ends it

**Decided by measurement. Unification is ruled out, not deferred** [PROBE].

A stream lives about five minutes and appending does not extend it (§9.1). The
whole point of the activity card is that it **outlives the work**: it is what a
channel has instead of silence while a turn delegates, or thinks, or grinds
through a long tool sequence. A ceiling of five minutes means precisely the
turns the card exists for are the ones whose card would die in the middle of
them — the plan freezing at whatever it said five minutes in, while the work
carries on for another twelve, and the "Turn finished" state never arriving.
That is worse than two messages. It is a card that lies.

Note that the interrupt (above) is no longer the binding constraint; it is only
the first one to be reached. Even with no interrupt at all, and even if a stream
could be reopened, five minutes is short of what the card has to cover.

So the two messages stay two messages, and the machinery §6.2 hoped to delete —
`_post_activity_card_later`, `activity_card_min_edit_seconds`, the alias map —
keeps earning its place. `chat.update` has no such ceiling, which is the
unglamorous reason the card is on the right API already.

This should not be revisited on the assumption that expiry might be generous. It
is not. If unification is wanted later it needs a mechanism that survives a long
turn, and §11 describes one: an Agent Session's `processing` status times out
after **an hour**, not five minutes [DOCS]. That is a different layer with a
different clock, and it is the argument for sessions rather than for reopening
this.

Two smaller open points:

- **`pending`.** The connector established empirically, against a live
  workspace, that a `task_card` accepts exactly three statuses standalone and a
  fourth, `pending`, only when nested in a `plan` — and it wraps every card in a
  plan for that reason. The docs give `task_update` three statuses
  (`in_progress`, `complete`, `error`); the SDK's `TaskUpdateChunk` comment lists
  four including `pending`. The two disagree. `task_display_mode="plan"` renders
  task updates inside a plan block, so `pending` may well work — untested.
  Without it, an untouched todo has no honest status.
- **Turns with no answer.** A turn that dies before producing any delta has no
  stream. It can still open one and immediately stop it, which is a fine
  outcome, but it means the card path cannot assume a stream already exists.
- **Field limits.** `task_update` and `plan_update` chunk fields cap at 256
  characters [DOCS]. The connector's `_MAX_CARD_DETAILS_LENGTH` is 2000, and the
  harness-error `rich_text_preformatted` is clamped to that. If the 256 limit
  applies to `details`, the harness error must be re-clamped or moved. Untested.

## 7. The failure modes we already have

### 7.1 `msg_too_long` on the closing rewrite

Largely dissolves. `markdown_text` is capped at 12,000 characters per call
[DOCS], three times `chat.update`'s 4,000, and **no total cap for a finalized
streamed message is documented anywhere** (searched; §9.3). The chain that makes
an answer vanish today — clamp to 4,000, size the first chunk to 4,000, split
the rest, one refused rewrite loses everything — mostly stops applying.

`_clamp_stream_preview` and `_STREAM_TRUNCATION_SUFFIX` become unnecessary on
the streaming path: an append does not need to fit the whole answer, only the
new part.

### 7.2 The repost fallback gated on `cron is not None`

`_post_root` reposts a refused rewrite as a fresh message only for cron pushes.
A streamed reply whose closing rewrite is refused raises `SlackDeliveryError`
with `chunks_sent=0` and the answer is gone.

Streaming changes the shape of this rather than fixing the gate. Appends are
**additive and already landed** — if `stopStream` fails, everything appended is
still on screen and still correct. The worst case is a message left in streaming
state with the trailing blocks missing, not an answer lost. That is a real
robustness gain, and it makes the ungated repost less urgent.

It does not make it unnecessary. If `startStream` itself fails, the existing
`SlackStreamError` path already falls back to ordinary posting — "streaming is
an optimisation, and the reply is still delivered in full by the ordinary
posting path" — and that stays the right design.

### 7.3 Edits re-sending the whole accumulated text

Gone. Today every debounce window re-sends the entire answer so far; a
3,000-character answer streamed over twenty windows sends roughly 30,000
characters of redundant payload. Append sends the delta only.

### 7.4 Out-of-order multi-part delivery

Substantially mitigated, from two directions: one ordered stream instead of two
independently tracked messages (§6.2), and far fewer parts because of the larger
ceiling (§7.1).

### 7.5 New failure modes to handle

| error [DOCS] | meaning | handling |
| --- | --- | --- |
| `stopped_by_user` | the reader stopped the stream from the UI; no further appends accepted | latch `failed`, post the remainder as a fresh message. **New user-visible behaviour with no analogue today.** |
| `message_not_in_streaming_state` | stopping something already stopped, or expired | latch and fall back |
| `message_not_owned_by_app` | wrong app | fatal, log |
| `missing_recipient_user_id` / `missing_recipient_team_id` | channel stream without a recipient | must not happen; see §8.3 |
| `streaming_state_conflict` [PROBE] | `chat.update` aimed at a message that is *still streaming*. In neither the SDK nor any documentation page | the opposite of the rest: the stream is alive, so append rather than edit |

No `stream_expired` error code is documented, and none exists: **expiry surfaces
as `message_not_in_streaming_state`** [PROBE], now by mechanism rather than by
inference — two streams were left alone and both ended with exactly that code
(§9.1). What the code still cannot tell you is *why*, since a reader-initiated
stop produces it too.

## 8. Rate limits, and the identity that has to be plumbed

### 8.1 Tiers [DOCS]

| method | tier |
| --- | --- |
| `chat.startStream` | Tier 2 — 20+/min |
| `chat.appendStream` | **Tier 4 — 100+/min** |
| `chat.stopStream` | Tier 2 — 20+/min |
| `chat.update` | Tier 3 — 50+/min |
| `chat.postMessage` | Special Tier — "generally allows posting one message per second per channel, while also maintaining a workspace-wide limit" |

The connector's throttles are justified by a comment that says "Slack meters
message operations at roughly one per second per channel, and `chat.update`
draws on the same budget as the posts that carry the reply itself." Per the
tiers, `chat.update` is Tier 3, not the Special Tier — so the current 1s spacing
is conservative even for what it does today.

`appendStream` at Tier 4 is twice `chat.update`'s allowance and is **not** in the
Special Tier; the rate-limits page mentions none of the three streaming methods
and states no per-channel rule for them.

### 8.2 What can relax, and what should not

A single stream at 1,000 ms debounce spends 60 appends/minute — already inside
Tier 4's 100+. Dropping the debounce to ~500 ms and the per-channel spacing to
~0.5 s puts one stream at ~120/min, at the edge. Recommendation: **debounce
600 ms, per-channel spacing 0.6 s**, which roughly halves latency-to-screen
while leaving headroom.

Two cautions. Slack tiers are per app per workspace per method, so the per-channel
spacing must not simply be deleted — several concurrent streams share the 100/min,
and `_wait_for_stream_slot`'s keying by channel remains the right shape but wants
a workspace-level guard beside it. And Tier 4's burst behaviour is undocumented;
"100+ per minute" is a floor, not a contract.

### 8.3 The recipient, and the thread — both mandatory, both measured

Four calls settle what three pages of reading could not [PROBE]:

| `chat.startStream` called with | answer |
| --- | --- |
| `thread_ts: ""` | `invalid_thread_ts` |
| `thread_ts` omitted entirely | `invalid_thread_ts` |
| a real `thread_ts`, `recipient_user_id` only | `missing_recipient_team_id` |
| a real `thread_ts` and **both** recipient ids | ok |

Two conclusions, and one of them reverses what the rest of this section
originally said.

**Both recipient ids are required, not one.** The heading this section carried —
"`recipient_user_id` is the one thing that must be plumbed" — was wrong by one.

> "recipient_user_id — Optional — The encoded ID of the user to receive the
> streaming text. **Required when streaming to channels.**" [DOCS]

> "recipient_team_id — Optional — The encoded ID of the team the user receiving
> the streaming text belongs to. **Required when streaming to channels.**"
> [DOCS]

Both carry a `missing_recipient_*` error, and the third row above is what one
without the other actually earns. Neither is required for a DM.

This lands on the known gap that user identity is dropped in the runtime, but
**the connector does not need the runtime for it.** Both inbound paths already
build the ids: `slack_team_id` and `slack_user_id` are set in the message
metadata at `slack_connect.py:6353`/`6359` and `6558`/`6564`. And the session id
carries them structurally — a DM session is
`slack_{team}_{channel}_{user}`, so `user_id` is recoverable by parsing, exactly
as `_extract_delivery` already parses that string for the channel. A channel
session is `slack_{team}_{channel}_{root_thread_ts}` and carries the team but not
the user — and channels are precisely where the recipient is required.

So one small piece of connector-side state is needed: remember the requesting
user against the request or session id at inbound time, read it at stream-open
time. There is ample precedent — `_SlackPendingQuestion`, `_SlackCronRecord` and
`_activity_records` are all exactly this. Roughly 60 lines, no runtime change,
no app-config change.

### 8.4 `thread_ts` is a blocker after all, and the reference page is wrong

This section previously read: "`thread_ts` is **not** a blocker despite being a
non-optional keyword in the SDK signature. The docs mark it Optional with only
soft guidance ... and no error enforces it. Pass the empty string." **Every
clause of that is wrong** [PROBE], and it is worth being precise about how,
because it is the clearest case in this document of a reference page not
describing the API it documents:

- the [`chat.startStream` reference](https://docs.slack.dev/reference/methods/chat.startStream)
  lists `thread_ts` under **Optional Arguments** [DOCS]. It is not optional:
  omitting it is refused [PROBE];
- its errors table does **not contain `invalid_thread_ts` at all** [DOCS] — the
  error the method returns for both failing cases [PROBE];
- the SDK's non-optional keyword, which this document read as an SDK quirk to
  be worked around, turns out to be the only source of the three that had it
  right [SDK].

So a stream is a threaded reply or it is nothing, and the guidance beside the
argument — "Streamed messages should always be replies to a user request" —
describes a constraint rather than a preference. Two adjacent errors in the same
table point the same way: `restricted_action_non_threadable_channel` and
`restricted_action_thread_only_channel` [DOCS].

**What that costs this connector.** It already computes two values and the
difference between them is exactly the problem:

```python
root_thread_ts  = str(event.get("thread_ts") or message_ts).strip()   # never empty
reply_thread_ts = ""
if is_dm:
    reply_thread_ts = str(event.get("thread_ts") or "").strip()       # empty at DM top level
elif self.config.reply_in_thread:
    reply_thread_ts = root_thread_ts
```

`reply_thread_ts` is what a reply is posted with, and it is empty in two places:
a DM answered at the top of the conversation, and a channel whose operator set
`reply_in_thread: false`. Everywhere else — every channel under the shipped
`reply_in_thread: true`, and every DM the user opened a thread in — it is
non-empty and a stream can be opened with it. `root_thread_ts` is never empty, so
a stream *could* be opened in both of the awkward cases, under the user's own
message.

**Recommendation: do not.** Streaming follows threading — it is available exactly
where the connector already replies in a thread, and `reply_in_thread` is the
lever that turns it on for a channel. Three reasons, in order of weight:

1. **It would split the turn across two places.** Phase 1 deliberately leaves the
   activity card as a message of its own (§4.2), and the card is posted with the
   same `reply_thread_ts` — so it would stay at the top level while the answer
   went into a thread hanging off the user's message, behind a "1 reply"
   affordance. The reader would watch a card report progress on an answer they
   have to click to find. That is worse than the flat, un-previewed reply they
   get today, and it is a cost the "replies become threaded" framing does not
   convey.
2. **In a channel it would override an operator's setting.** `reply_in_thread:
   false` is written down on purpose. Threading a reply so that an optional
   preview becomes possible puts the feature in charge of the setting.
3. **The DM case is not actually measured.** The probe was run in a channel. The
   reference treats DMs differently in the immediately adjacent argument — the
   recipient ids are required "when streaming to channels" — and describes
   `channel` as "An encoded ID that represents a channel thread **or DM**"
   [DOCS]. Whether a DM stream needs a `thread_ts` at all is therefore open, and
   declining to stream costs nothing if the answer turns out to be no: the guard
   is one condition and relaxing it is one line.

**The one probe that would have changed this answer has been run, and it does
not work** [PROBE]. `reply_broadcast` makes a threaded `chat.postMessage` appear
in the conversation's main flow as well as in the thread, which is precisely
what would have made a DM's streamed top-level reply visible where the reader is
looking. `chat.startStream` with `reply_broadcast: true` returns
`{"ok": true, ...}` — and `conversations.history` afterwards shows only the
thread root, not the streamed reply. **Accepted and silently ignored.** The
`ok: true` means the SDK merged an unknown keyword into the payload and the
server tolerated it, not that it was honoured; there is no error to notice.

So the recommendation stands, and this is closed rather than open: the objection
that decided it — the card at the top level while the answer hides behind a "1
reply" affordance — cannot be removed this way, and should not be revisited on
the hope that it can.

Until then the connector refuses the attempt before making it, rather than
spending a call and a turn's latency to be told `invalid_thread_ts`.

## 9. What could not be settled, and what needs a test workspace

Stated plainly, because several of these gate the recommendation.

**Three of these are now closed** [PROBE]. Item 10 is answered: `chat.startStream`
returns `ok` for this app on this workspace with nothing but `chat:write`, so
the method is available and the absence of gating language in §3 was reporting
the truth. And two questions this list never thought to ask were answered
against it — that `thread_ts` is mandatory and that both recipient ids are
(§8.3, §8.4) — which is the argument for running the rest of these rather than
reasoning further about them. Two additions to the list, both cheap:

11. **Whether a DM stream needs a `thread_ts`.** The probe ran in a channel, and
    the reference treats DMs differently in the adjacent argument (§8.4).
12. ~~**Whether `chat.startStream` accepts `reply_broadcast`.**~~ **Measured:
    accepted and silently ignored** [PROBE]. `ok: true`, and the message does
    not appear in the conversation's main flow. §8.4 is closed by it rather than
    reopened.
13. ~~**Whether a Markdown construct spanning two appends survives.**~~
    **Measured: yes** [PROBE]. `- one\n`, `- two\n` and `- three\n` in three
    separate appends produce one `rich_text_list` with three items, identical to
    sending them whole; the same holds for ordered lists and blockquotes. So
    Slack re-converts the accumulated text rather than each chunk in isolation,
    and §9.4's "converts per call" is about what a call *contains*, not about
    where the boundaries fall.

    This holds for splits at complete line boundaries, which is what
    `streamable_prose_prefix` guarantees anyway — so the boundary keeps earning
    its place for the sub-line case (`**bo` / `ld**`) and no longer needs to
    carry the multi-line one.

1. ~~**Stream expiry duration. Undocumented.**~~ **Measured: about five
   minutes, as a total-duration cap, and appending does not extend it**
   [PROBE].

   | probe | append cadence | last success | first failure | error |
   | --- | --- | --- | --- | --- |
   | 1 | every 60s | 4.3 min | **5.30 min** | `message_not_in_streaming_state` |
   | 2 | every 10s | ~5.1 min | **5.18 min** | `message_not_in_streaming_state` |

   Six times the append rate, death within seven seconds of the same elapsed
   time. The idle-timeout reading that probe 1 alone allowed — every append sat
   at exactly the interval that could itself have *been* the threshold — is
   ruled out by probe 2, which appended 29 times inside the window and expired
   anyway.

   Treat ~5 minutes as an observed floor for this workspace, **not a documented
   guarantee**: Slack publishes no number, so it is a fact about what to expect
   and not a value to compute with. Nothing in the connector holds it as a
   constant.

   It is unaffected by `task_display_mode`: in plan mode, 14 appends over 283s
   did not extend it and the 15th at t+303s failed the same way [PROBE]. So it
   is not something the Phase 2 shape would have escaped.

   The consequence is larger than the number. Turns here routinely run past five
   minutes — one ran 17m43s — so **a stream ending part-way through a turn is
   the ordinary case, not an edge**, and the expiry fallback is the normal path.
   It is also what rules Phase 2 out rather than merely blocking it (§6.3).
2. ~~**Whether `chat.update` works on a message still in streaming state.**~~
   **Measured, and the answer is the useful one** [PROBE]: refused on a live
   stream with `streaming_state_conflict`, accepted once the stream has expired.
   Three things follow.

   A streaming message is **exclusively owned by the streaming API while it is
   open** — the two do not interleave, so any edit aimed at a live stream is
   refused. Nothing in this connector aims one there: the activity card is a
   message of its own and `send()` declines to rewrite a streamed ts.

   A refused edit is a **clean no-op** — an append made immediately afterwards
   succeeded and the stream was unharmed — so a stray edit costs an error and
   nothing else.

   And the lock **releases on expiry**, which is what lets an expired stream be
   rewritten whole rather than having its tail posted beside it. The reply stays
   one message and expiry becomes invisible to the reader. The bound on that is
   `chat.update`'s 4,000 characters against an append's 12,000: a stream that
   ran its full five minutes may well hold more than an edit could put back, and
   a rewrite that cannot fit must decline rather than clamp — clamping a closing
   rewrite to 4,000 is what silently dropped an entire answer on 2026-08-20.
3. **Total finalized message length.** Not documented. Only the 12,000-per-call
   field limit is given. If there is an undocumented total, the splitting logic
   cannot simply be relaxed.
4. ~~**Whether `markdown_text` accepts real Markdown or Slack's mrkdwn
   subset.**~~ **Measured: real Markdown, converted server-side** [PROBE].
   `**bold**` was sent and Slack stored `*bold*`, building `blocks` from it. A
   streamed message therefore carries blocks in its stored form, not only text.

   **The reverse direction was then measured too, and it is a defect** [PROBE].
   Exactly what `_normalize_slack_mrkdwn` produces was sent as `markdown_text`
   and read back:

   | sent | stored | structure |
   | --- | --- | --- |
   | `*bold-in-mrkdwn*` | `_bold-in-mrkdwn_` | `text[italic]` |
   | `\u2022 bullet item` + 3 following lines | — | `rich_text_list`, and **all three following lines absorbed into the same list item** |
   | `<https://example.com|labelled link>` | unchanged | `link` |
   | `_italic_`, `` `code` `` | unchanged | as written |

   The first is a style defect: every `**bold**` the normaliser turns into
   `*bold*` renders as emphasis. The second is structural and worse — the
   substituted bullet character opens a `rich_text_list` that swallows whatever
   follows it into one item, which reads as a rendering bug with no obvious
   cause. Both would have shipped.

   **So mrkdwn must not be sent into `markdown_text`**, and the fix is the
   simplification originally hoped for, arrived at from the opposite direction:
   the streaming path sends the Markdown the model wrote and Slack converts it.

   That makes the dialect a property of the destination rather than of the text.
   `markdown_text` reads Markdown; `chat.postMessage`, `chat.update` and every
   Block Kit `section` read mrkdwn. The connector converts at the boundary
   between them rather than up front, which is four places: a blocks chunk at
   the close (Block Kit, so mrkdwn), the rewrite of an expired stream (an
   ordinary edit, so mrkdwn — including the part Slack already converted for
   itself, because that call replaces it), the message posted beside a dead
   stream (mrkdwn), and the retry that returns to the streaming API after a
   `streaming_state_conflict` (Markdown).

   Two smaller findings. Slack's own `<url|label>` **is honoured inside
   `markdown_text`**, so a mention or channel link in the agent's own text
   crosses untouched — which is what makes the boundary tractable at all. And a
   streamed message stores `blocks`, not only text, which is why the rewrite
   must send an explicit empty `blocks` list rather than text alone.

   What remains unmeasured is the rest of the normaliser: headings, links,
   labelled bullets and blockquotes were never sent. They are handled the same
   way — passed through as written — but on inference from these three, not on
   measurement. **Also unmeasured, and the next thing worth a probe: whether a
   Markdown construct spanning two appends survives.** Slack converts per call,
   so a list whose items arrive in separate appends may or may not become one
   list. The connector cuts at complete lines, which bounds the exposure to
   multi-line constructs and is why that boundary is kept even though raw text
   no longer needs it for prefix stability.
5. ~~**Whether `data_visualization` and `data_table` are accepted inside a
   blocks chunk**~~ **Measured: yes, both** [PROBE], on append and on stop. The
   only block type that does not stream is `file`, which faults with
   `internal_error` and is unreachable from here (§5.3).
6. **Whether `task_update` accepts `pending`** — docs say three statuses, SDK
   comment says four, and the connector's own live-workspace testing found the
   fourth works only nested in a plan (§6.3).
7. **Whether the 256-character chunk limit applies to `task_update.details`**,
   which would force re-clamping the harness error from 2,000 (§6.3).
8. **Whether the 50-block chunk budget is per call or cumulative across the
   stream.** The wording — 50 via chunks plus 50 at stop for 100 total — reads
   cumulative, which would matter for a long answer with many tables.
9. **Tier 4 burst behaviour** (§8.2).
10. **General availability.** The evidence is the absence of gating language, not
    a positive statement (§3). A test workspace settles it in one call.

Items 4, 5, 6, 7 and 10 are answerable with a handful of calls against a
throwaway workspace and would collapse most of the remaining uncertainty. Items
1, 2, 3 and 8 need a deliberately long or large run to observe.

## 10. Work involved

Phase 1 — stream the answer. Card unchanged.

| # | work | rough size |
| --- | --- | --- |
| 1 | `_SlackStreamingSurface` over `start`/`append`/`stop` | ~150 |
| 2 | move snapshot rendering into the surface; prefix-stable raw text for the streaming one (§4.3 leak 1) | ~60 |
| 3 | remember `recipient_user_id` **and** `recipient_team_id` at inbound, read at open, and refuse a stream that has neither a thread nor both ids (§8.3, §8.4) | ~90 |
| 4 | invert the terminal delivery; keep `send()`'s raise contract intact (§4.3 leak 2) | ~150, the risky one |
| 5 | mode-aware chunk splitting in `send()` (§4.3 leak 3) | ~50 |
| 6 | ordered chunk composition — prose to `markdown_text`, tables and charts to blocks chunks — as a variant of `render_blocks`'s existing segmentation (§5.4) | ~120 |
| 7 | new error handling: `stopped_by_user`, `message_not_in_streaming_state`, retry-without-blocks on a chunk (§5.3, §7.5) | ~60 |
| 8 | the internal `off` / `edit` / `stream` ladder and the fallback between its rungs; `enable_streaming` stays a boolean in all three shipped templates, which must each list the key or an upgrade deletes it from the operator's file | ~60 |
| 9 | tests | see below |

Roughly 700 lines of connector. Tests are the larger half: `test_slack_streaming.py`
is 483 lines across 20 tests, every one of them written against post-then-edit
and asserting on `chat_update` calls; expect a near-total rewrite plus new
coverage for the §7.5 errors, the recipient plumbing and the block-chunk
fallback. Call it 400–600 lines of test. `test_slack_channel.py` (3648 lines)
will have chunk-count and message-count assertions that move.

~~Phase 2 — unification.~~ **Not being done** (§6.3.1). §9.1 was the gate and
answering it closed the door rather than opening it: the ~250–300 lines are not
work deferred, they are work avoided, and the machinery §6.2 hoped to delete
keeps earning its place instead.

What replaces it on the roadmap is smaller and is not about the card: **delete
`edit`** once `stream` has run in production (§4.2), which subtracts rather than
adds.

Phase 1 needs no app-configuration change, no new scope, and no runtime change.

## 11. Agent Sessions, and where this work sits relative to it

Asked after the rest of this document was written: Slack's
[Agent Sessions](https://docs.slack.dev/ai/agent-sessions/) appears to supersede
the older `assistant.*` API and offers, among other things, a native stop
button. Does the streaming design above still earn its place?

**Yes, and the two are not alternatives.** Agent Sessions is a lifecycle and
chrome layer that sits *above* the same three streaming calls; it does not
replace them, and its own documentation says `chat.startStream` is one of the
two ways to drive it. The two clocks say the same thing: a session's
`processing` status times out after an hour [DOCS], a stream after about five
minutes [PROBE]. That is not a contradiction, it is the division of labour —
sessions carry the long-running work, streams carry the immediate response. Adopting it later would add methods, not rewrite the ones
Phase 1 builds. But it is not free, it is one day old, and the installed SDK
cannot call it at all.

Note the dates. The Agent Sessions API and the deprecation timetable below were
announced on **2026-08-20** — the day before this section was written. Anything
in it may move.

### 11.1 What it is [DOCS]

A session is a conversation with an agent that Slack tracks in its own right,
"scoped to a single thread in a conversation, like a channel or DM". It carries
a **status**, a **title**, an initiator, and — while it is working — a **stop
button**. There is no opaque session id: the key is the channel plus the thread,
which is the same pair this connector already uses to key a stream.

Two methods, on the `agents` namespace:

| method | what it does |
| --- | --- |
| [`agents.sessions.setStatus`](https://docs.slack.dev/reference/methods/agents.sessions.setStatus) | sets the lifecycle status, and **creates the session if there is none** |
| [`agents.sessions.rename`](https://docs.slack.dev/reference/methods/agents.sessions.rename) | sets the title (≤200 characters) |

Four statuses: `processing` ("The agent is working on a user's task. A stop
button is shown to the user."), `active`, `suspended` (waiting on the user),
`closed`. A session in `processing` **times out after one hour** and reverts to
`active` — twelve times the measured stream expiry of §9.1, and a different
clock on a different object. The gap is the point: it is why a session can front
a turn that a stream cannot (§6.3.1).

Two events: [`agent_session_stopped`](https://docs.slack.dev/reference/events/agent_session_stopped)
and [`agent_session_title_changed`](https://docs.slack.dev/reference/events/agent_session_title_changed)
— readers can rename a session from the UI.

### 11.2 What it costs

**Scope.** Neither `agents.sessions.*` reference page lists `assistant:write`;
both say `chat:write` [DOCS]. The requirement is one level up:

> "Only apps declared as agents in the app settings (which requires the
> `assistant:write` scope) can create sessions."
> "The `chat:write` scope is also required to manage thread-based sessions."
> — [Agent sessions](https://docs.slack.dev/ai/agent-sessions/) [DOCS]

and the developer guide is explicit that the scope comes with the feature rather
than being requested for the methods: "The `assistant:write` scope is needed for
this, and thus is automatically added to your app when you enable the feature in
the app settings" [DOCS]. So the operator's reading is right in effect —
`assistant:write` is required — but it is a property of declaring the app an
Agent, not a per-call grant. Either way it is **an app-configuration change this
workspace has not made**, and scope grants here are not automatic: the bot token
already fails `missing_scope` on `conversations.info` and `conversations.list`.

**Plan and audience** [DOCS]. From
[Developing agents](https://docs.slack.dev/ai/developing-agents/): "Developing
and using some AI features require a paid plan, despite being visible in the app
settings on any plan", and "Workspace guests are not permitted to access apps
with the Agents feature enabled". Neither applies to `chat.*` streaming (§3).
The literal words "beta" and "early access" appear on none of the pages read.

**The SDK cannot call it** [SDK]. `slack_sdk` 3.43.0 — which is also the newest
released version — has **no** agent-session method. A grep for `agent_session`
and `agentSession` across the whole installed package returns nothing, and the
only assistant-named methods are the three thread decorators
(`assistant_threads_setStatus` / `setTitle` / `setSuggestedPrompts`), none of
which this connector uses. `slack_bolt` 1.30.0 is the same. Adopting sessions
today means hand-rolled `api_call("agents.sessions.setStatus", ...)` — workable,
and exactly the kind of thing that has to be rewritten when the SDK catches up.

**Message shape.** A session is scoped to a thread, but nothing in the
documentation says the app may not post elsewhere while one is open, and
`chat.postMessage` / `chat.update` remain explicitly supported inside a session
(§11.3). The docs do not say either way whether interactive Block Kit elements
behave differently inside a session's message.

### 11.3 They compose; they do not compete [DOCS]

Two sentences from the Agent Sessions page settle it:

> "The `chat.startStream` method creates a session if one doesn't exist, and
> sets the session status to `processing`."

> "Agent sessions do not require using the streaming API methods. You can
> instead use the `agents.sessions.setStatus` method with the `chat.postMessage`
> method and the `chat.update` method. However, when not using the streaming API
> methods, your app must call the `agents.sessions.setStatus` method to manage
> the session status, and the `agents.sessions.rename` method to manage the
> title, as there is no implicit state management."

So streaming is the *preferred* driver of a session, not a competitor to it: it
manages the status implicitly, and the post-and-edit path does not. That is a
second, independent argument for Phase 1 — and against keeping `edit` — from a
direction this document had not considered.

**Nothing streaming-related is deprecated** [DOCS]. Direct fetches of
`chat.startStream` and `chat.stopStream` carry no deprecation banner; the trio
launched 2025-10-07 and was still being extended in April and June 2026. What
*is* being replaced is the `assistant.threads.*` surface: the
[20 Aug 2026 changelog](https://docs.slack.dev/changelog/2026/08/20/agent-updates)
puts the `assistant_view` messaging experience on a **February 2027**
deprecation, and the
[migration guide](https://docs.slack.dev/ai/migrating-to-agent-messaging/) maps
`assistant.threads.setStatus` and `setTitle` onto `agents.sessions.*`. **This
connector calls none of the three**, so that deprecation costs it nothing.

### 11.4 The stop button, and what `stopped_by_user` actually is

This is the sharpest difference between the two layers, and the answer is not
the flattering one.

- **With a session** [DOCS]: the stop button is native, Slack draws it while the
  status is `processing`, and pressing it fires `agent_session_stopped` with the
  channel, thread, message and user. The event page is emphatic: "All apps that
  manage agent sessions must handle this event; supporting stop is not
  opt-in." Slack does **not** move the status itself — the app must, via
  `agents.sessions.setStatus` or `chat.stopStream`.
- **Without one**: `stopped_by_user` appears in exactly one place in the whole
  documentation — the errors table of
  [`chat.appendStream`](https://docs.slack.dev/reference/methods/chat.appendStream)
  — as "The streaming message was stopped by the user and no further appends are
  accepted" [DOCS]. It is an error returned to the app. **No page reached
  describes any reader-facing way to stop a plain, non-session stream.** That is
  a "the documentation does not say", not a "there is no button": the error's
  existence implies an affordance somewhere, but nothing has been observed
  rendering it, and §7.5 handles the code on the assumption that it can arrive.

So the honest position is: a reader-facing stop is **documented only for Agent
Sessions**. Phase 1 handles `stopped_by_user` because the error exists and
losing an answer to an unhandled one would be worse than handling a code that
never fires — not because a button has been seen.

### 11.5 Would Phase 1 have to be rewritten? No

Phase 1 builds `chat.startStream` / `appendStream` / `stopStream` behind a mode
flag, a prefix-stable append source, a recipient lookup, and error handling that
already includes `stopped_by_user`. Adopting sessions later adds:

- two calls (`setStatus`, `rename`) and two event subscriptions, hand-rolled
  until the SDK carries them;
- a status transition at the turn's start and end — which the connector already
  has the events for, since `_track_activity_event` sees every one of them;
- a handler for `agent_session_stopped` that does what the `stopped_by_user`
  latch already does: stop appending, deliver the remainder, mark the turn.

None of that changes how the answer is written into the message. **This work is
a stepping stone, not throwaway and not orthogonal**: the session layer is
driven by the very calls Phase 1 makes, and the `stopped_by_user` handling is
the same handling `agent_session_stopped` would need.

Phase 2 is no longer a piece to reconsider: it is abandoned on a measurement
that has nothing to do with sessions (§6.3.1). What sessions change is the
prospect of ever revisiting it. A session's own status chrome overlaps what the
activity card renders by hand, and its `processing` status times out after an
hour rather than five minutes — so if the card is ever to be folded into
something Slack draws, **the session is the thing to fold it into, not the
stream**. That is a direction, not a plan, and it costs the app-configuration
change of §11.2.

### 11.6 How many live delivery paths the end state has

§4.2 originally argued that `edit` must not live forever, because two live
paths diverge and this connector has produced defects exactly that way. That
argument lost, on measurement rather than on preference: `stream` cannot reach a
reply with no thread, so `edit` is permanent (§4.1.1). Agent Sessions changes
nothing here, because **it is not a delivery path at all**. Counting what
actually writes a reply into Slack:

| | before Phase 1 | Phase 1 shipped | sessions adopted |
| --- | --- | --- | --- |
| ordinary post-and-chunk (`send()`) | 1 | 1 | 1 |
| previewed reply | 1 (`edit`) | 2 (`edit`, `stream`) | 2 (`edit`, `stream`) |
| **live delivery paths** | **2** | **3** | **3** |

Sessions add a lifecycle layer over the streamed rung, not a fourth way of
putting text on screen. Three is where this settles, and the third is earned
rather than transitional — what makes it tolerable is that the rung is chosen in
one place on measured conditions, not that it is temporary.

### 11.7 The two ideas the operator is weighing

**A reader-facing stop or pause.** Available in a documented, supported form
**only through Agent Sessions**, at the price of the app-config change in §11.2.
On the plain path there is a latch for `stopped_by_user` and no way to know
whether a reader can produce it. If the stop button is the goal, sessions are
the way to get it, and Phase 1 is the layer it would sit on.

**Buttons on the activity card for extra input mid-turn.** One measured fact
from today, on the current path: an `action_id` survived three `chat.update`
rewrites of a card and routed correctly ~40 minutes later. So card controls are
viable now, on the message the card already uses, with no session and no new
scope. What is **not** known is whether interactive blocks survive inside a
*streamed* message — that is item 5's neighbour on the §9 test-workspace list
and nothing in the documentation answers it. Since Phase 1 deliberately leaves
the activity card as a separate `chat.postMessage` / `chat.update` message
(§4.2), mid-turn buttons are unaffected by this work either way, and can be
built on the card today without waiting for any of it.

### 11.8 Where the sources disagree

Three places, all flagged rather than resolved, because two trees disagree and
neither can be tested without a workspace:

1. **`session_status` on `chat.stopStream`.** The Agent Sessions guide was read
   as describing a `session_status` parameter defaulting to `active`. A direct
   fetch of the `chat.stopStream` reference page shows no such argument — its
   arguments are `token`, `channel`, `ts`, `chunks`, `markdown_text`, `blocks`,
   `metadata` and nothing else. Do not build on it.
2. **`thread_ts` on `chat.startStream`. Settled, in the guide's favour**
   [PROBE]. The reference page marks it Optional; the Agent Sessions guide says
   startStream "requires `channel` and `thread_ts`"; the SDK declares it a
   keyword with no default [SDK]. Two of the three were right and the reference
   page was wrong — see §8.4. Worth carrying forward as a general caution about
   which of these trees to trust: on this argument the narrative guide and the
   SDK beat the reference.
3. **Whether `chat.startStream` creates a session.** The Agent Sessions guide
   says it does. The `chat.startStream` and `chat.stopStream` reference pages do
   not mention agent sessions at all. The narrative and the references have not
   been reconciled by Slack. If the guide is right, a Phase 1 deployment on an
   Agent-declared app would begin creating sessions implicitly — which is worth
   watching for, and is not something this workspace can trigger, since the app
   is not declared an agent.
