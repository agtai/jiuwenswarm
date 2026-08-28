# Slack "digest" interference: what the report could mean, and what is real

Investigation of a second-hand remark that Slack's "digest" feature "could
interfere sometimes with our other skills". No incident, no specifics. This
document establishes which feature was plausibly meant and whether any of the
candidates can reach us.

Read-only investigation: no source changes, no config changes, no Slack API
calls. Code claims cite `file:line` against `c74daa3a8` (`local/deployed`).

## Summary

The connector is not reachable by any Slack-generated summary. Every Slack AI
summarisation feature renders privately to one user and posts nothing into a
channel; the one exception that does write into a channel (huddle threads)
carries a subtype our filter already drops.

The history-reading angle is real but the culprit is not Slack. Our own history
toolkit does not exclude any message from what the digest skills read: not other
apps' messages, not system subtypes, and not our own prior digests. Since
`repository-activity-digest` posts reports into a channel and
`slack-channel-digest` reads that same channel's history, our digests are
already feeding our digests. That is the most likely referent of the remark, and
it is a real effect independent of anything Slack does.

Confidence that no *Slack* feature reaches the connector: high, from Slack's own
documentation. Confidence about which feature the colleague meant: low — the
remark is too thin to attribute, and "digest" is a word that appears in our own
skill names and config keys as much as in Slack's vocabulary.

## Candidate features, and where their output goes

The crux is a single distinction: a per-user rendering never becomes a message,
so it can never reach a connector that consumes message events. Only something
posted *into* a channel matters.

| Candidate | Delivery | Reaches connector? |
| --- | --- | --- |
| Recap (daily channel recaps) | Sidebar, per user | No |
| Conversation / channel summaries | Per user, on demand | No |
| Search answers, auto filters | Per user, in search results | No |
| File summaries | Per user, below the file | No |
| Message translations | Per user, explicitly private | No |
| Notification schedules, bundled email | Per-user notification setting | No |
| Huddle notes / transcripts | Canvas in a huddle thread, in-channel | Message exists, filtered by subtype |

Slack's guide to AI features describes each of these as rendering to the
requesting user. Recap is reached by clicking "Recap in the sidebar"; summaries
appear behind a Summarize control ("Your summary will appear when it's ready");
translations are stated outright as "only visible to you, so other people will
always see the original message".

- https://slack.com/help/articles/25076892548883-Guide-to-AI-features-in-Slack
- https://slack.com/help/articles/27918234552979-Tips-for-working-with-Slack-AI

Notification digests are a per-user delivery preference — bundled email
notifications "sent once every 15 minutes or once an hour", plus notification
schedules. Nothing is written to a channel.

- https://slack.com/help/articles/201355156-Configure-your-Slack-notifications
- https://slack.com/help/articles/360025446073-Guide-to-Slack-notifications

Huddles are the only candidate that produces an in-channel artefact. Huddle
notes "will be shared in a canvas in the huddle thread", and the huddle thread
"will automatically be saved as a message thread in the DM or channel where it
started".

- https://slack.com/help/articles/31377193680019-Use-AI-to-take-huddle-notes-in-Slack
- https://slack.com/help/articles/4402059015315-Use-huddles-in-Slack

## 1. Can any of it reach the connector?

No, for every candidate.

For the per-user features this is definitional: no message is created, so there
is no `message` event, so the connector never sees anything. The concern is
unfounded for Recap, channel summaries, search answers, file summaries and
notification digests. This does not depend on our filters at all.

For huddles a message does exist. It carries subtype `huddle_thread`. That
subtype is not in Slack's documented subtype list — it is real but
undocumented, visible in SDK type definitions (e.g. `slack-go`'s message struct
carries `huddle_thread` alongside `room`, `no_notifications`, `permalink`)
rather than in Slack's reference page.

- https://docs.slack.dev/reference/events/message/
- https://pkg.go.dev/github.com/slack-go/slack/slackevents

Our filter drops it regardless of what the subtype is called, because it
allow-lists rather than deny-lists:

- `slack_connect.py:81` — `_USER_CONTENT_SUBTYPES = frozenset({"file_share"})`
- `slack_connect.py:2514` — any message with a subtype outside that set returns
  early.

So `huddle_thread` is dropped by the same branch that drops `channel_join` and
`message_changed`. This is robust to Slack inventing new subtypes: an unknown
subtype is dropped by default. Documented behaviour plus code; not inferred.

## 2. Would such a message carry `bot_id` or a real user id?

Moot for the per-user features. For huddle threads the attribution question
never arises, because the subtype check at `slack_connect.py:2514` fires before
attribution matters. The `bot_id`/`bot_profile` check (`:2508`) and the own-user
check (`:2511`) are additional layers that this case does not need.

Not determined, and not worth determining: whether a huddle thread message is
attributed to the huddle starter's user id or to a system identity. It changes
nothing, since the subtype gate is upstream of both.

## 3. Could a Slack summary trigger link detection?

The chain requires a Slack-generated message to survive filtering. It does not.

Link detection is not an independent entry point — it funnels through the same
handler that applies loop protection. The link route checks channel opt-in and
the URL regex, then calls `_handle_slack_event`, which runs the filter block at
`:2502-2515` before anything else. A huddle thread message containing links would
be dropped there, before the channel's prompt is appended at `:2555-2557`.

So the feared chain — Slack summarises a channel, quotes links from it, and our
link trigger registers items nobody posted — cannot occur. It requires two
independent things to be false at once: that the summary is posted as a message
(it is not, for every AI feature) and that it survives the subtype gate (it does
not, for the one feature that does post).

Worth noting the chain is not absurd in general. Any *app* that posts a
link-bearing summary into an opted-in channel would be a candidate, and is
likewise dropped — but by the `bot_id` check at `:2508` rather than by subtype.
Both paths are covered.

## 4. The history-reading angle — this is the real one

A message posted into a channel becomes part of that channel's history whether
or not the connector ever dispatched it. The connector's filters are irrelevant
here: they gate *dispatch*, not *reading*. The history toolkit is a separate
path and applies none of them.

The toolkit does not filter subtypes at all. The string `subtype` does not
appear anywhere in `jiuwenswarm/agents/harness/common/tools/slack_history.py`.
Everything `conversations.history` returns is a candidate record.

It does not exclude other apps' messages either. The only bot-awareness is
`_is_own_bot_message` (`slack_history.py:471-486`), and its result is written
into the record as a flag at `:616` — `"is_own_bot_message": ...` — not used to
skip anything. The record is built and returned regardless.

Two consequences, in increasing order of how much they matter:

**Huddle threads and system messages are read as content.** A huddle thread
entry sits in history with whatever text it carries, and the digest skills see
it as a record like any other. Low impact — these carry little text — but it is
the mechanism by which a genuinely Slack-generated artefact reaches a skill,
which is what the colleague may have half-remembered.

**Our own digests are read as content.** `repository-activity-digest` posts
scheduled reports into a channel as the bot
(`local_skills/repository-activity-digest/SKILL.md:82-85`, `post_as_root: true`
for recurring channel reports). `slack-channel-digest` reads channel history and
receives those reports as records flagged `is_own_bot_message: true` but not
removed. With `history_digest_channel_ids: ["*"]`, no channel is excluded from
this.

The second one deserves the attention. It is self-referential summarisation: a
digest of a channel that contains yesterday's digest can restate yesterday's
digest as though it were discussion. Nothing about it involves Slack's features.
It matches the reported symptom — "digest could interfere with our other skills"
— better than any Slack feature does, and it is the one finding here that is
actionable.

Whether the flag is *sufficient* is a live question rather than a defect on its
face: the model does receive `is_own_bot_message`, so a well-behaved skill could
choose to discount those records. Whether the skill prompts actually instruct it
to is not something this investigation settled, and it is the natural follow-up.

## 5. History API interactions

Slack summaries are not returned by `conversations.history` because they are not
messages. System events are — the method returns messages and "events that
happened within the channel".

Two limits worth recording, neither specific to digests:

- Rate limiting. Tier 3 (50+/min) historically, but "as of May 29, 2025, for new
  applications ... distributed outside of the Marketplace, this method is rate
  limited to 1 request per minute", with `limit` capped and defaulted to 15
  objects. Which tier this deployment's app falls under is not established here
  and depends on the app's registration date and distribution status.
- Free-plan truncation. `is_limited` is "only included for free teams that have
  reached the free message limit", indicating older messages exist beyond reach.
  This interacts with a known, separately-tracked weakness: claiming complete
  history coverage when Slack reported truncation.

- https://docs.slack.dev/reference/methods/conversations.history/

## Verdict

Terminology collision on the Slack side, real effect on ours.

No Slack "digest" feature can reach the connector. The per-user features produce
no message; the one in-channel artefact is dropped by an existing filter that
happens to be allow-list shaped and therefore robust to future subtypes. Points
1 through 3 are closed, from documentation rather than assumption.

The history-reading route is open, and it is open to *everything*, not to Slack
specifically. Our own digests are the most likely thing flowing through it.

What cannot be determined without workspace access, and exactly what to check:

- Whether Slack AI is enabled for this workspace at all. If it is not, the
  entire Slack-side question is moot. Check the workspace plan and whether the
  AI add-on is active — admin settings.
- Whether huddles are used in the opted-in channels (`C0BKHDWGTHT`,
  `C0BN2F6UDDH`, `C0BPP3XDX2A`, `C0BPLSPHHDZ`, `C0BKHE3AH4M`). If no huddles
  occur there, even the low-impact history contamination does not arise.
- Whether the workspace is on a free plan, which decides whether the `is_limited`
  truncation path is live.
- Which channel `repository-activity-digest` posts into, and whether
  `slack-channel-digest` is ever run against that same channel. This is the one
  worth checking first — it is the only route with a plausible path to real
  interference, and it needs no Slack admin access to answer.

The honest read of the original remark: most likely the colleague meant our
digest skills, not Slack's. The names collide, and our side is where an
observable effect actually exists.
