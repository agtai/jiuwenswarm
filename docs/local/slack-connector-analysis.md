> ## ⚠️ Status note — read before acting on anything below
>
> **Added to this branch 2026-08-04. The body below is preserved verbatim and is NOT updated.**
>
> This analysis was produced against a **different checkout** —
> `/home/ai/code/jiuwen/jiuwenswarm` at `5a7319a4` on branch `develop`, where the connector was 330
> lines with "one commit ever". **That is not this tree.** Here the connector is ~700 lines, there is a
> ~1,500-line `slack_history.py` that does not exist upstream at all, and roughly half the hint list in
> §6 has since been implemented — in two cases by a different design than the one proposed.
>
> Keep it for §2 (Slack platform capability inventory), §3 (the jiuwenswarm connector API) and §4 (what
> the other connectors implement). Those remain accurate and are the most expensive parts to
> reconstruct. Treat §1 (current implementation) and §6 (hints) as historical.
>
> ### Status of §6's hint list in this tree
>
> | # | Hint | Status here |
> |---|---|---|
> | H1 | Slack as cron target | ✅ **done** — `SLACK` in the enum, threaded through controller/store/runtime/tools, plus a `post_as_root` flag the hint never proposed |
> | H2 | Log the cron-target coercion | ✅ **done** — warning added in `_normalize_targets_str` only, membership tested via the validator so a valid `feishu_enterprise:<app>:chat:<id>` is not misreported |
> | H3 | Raise the 4,000-char cap | ✅ **done** — now 38,000; the splitter was already paragraph/line/word aware and `<…>`-token safe |
> | H4 | Reaction acknowledgement | ✅ **done** — `acknowledge_mode: reaction\|text\|both\|off`, default `reaction`; reacts to the request's own `ts`, not `thread_ts` |
> | H5 | `auth.test` at startup | ✅ **done** — plus an `authorizations` fallback and precise (non-greedy) mention stripping |
> | H6 | Passive channel reading | ⚠️ **partial** — a per-channel opt-in accepts non-mention messages, but only those containing an http(s) URL. No general `all\|mention\|reply\|off` mode yet |
> | H7 | Thread/channel history ingestion | ✅ **done, different design** — NOT `MessageStore`. An agent-facing toolkit (`get_current_slack_channel_history`) with pagination, `Retry-After` handling, redaction and user-name resolution, gated by `history_digest_channel_ids` and a fail-closed metadata filter |
> | H8 | Streaming via throttled `chat.update` | ✅ **done** — opt-in `enable_streaming`, per-channel gate rather than per-stream, on a `StreamingSession` shared with Feishu; intermediate edits best effort, the closing rewrite keeps the raise contract. Live rate-limit behaviour still unobserved |
> | H9 | Block Kit | ❌ not done — but a mrkdwn normalization layer exists (headings, bold, bullets, links, code-fence protection), which addresses much of the underlying complaint |
> | H10 | File exchange | ❌ not done |
> | H11 | Interactive approvals | ❌ not done |
> | H12 | Assistant-thread surface | ❌ not done |
> | H13 | Durable dedup | ❌ not done — still a 1024-entry in-memory LRU, though the dedupe key improved to `team:channel:msg_id` |
>
> ### Corrections to the body
>
> - §7 says upstream "has touched the Slack connector exactly once". Re-verified against
>   `upstream/develop` at `ccdf2647` (148 commits later): `slack_connect.py` still has **zero** upstream
>   churn, and only two upstream commits mention "slack" at all, neither touching the connector. The
>   rebase was a clean replay — that risk did not materialise.
> - §5.2 lists "`from_dict` coerces unknown target → `web` without logging" as an open defect. Fixed.
> - §2 is flagged in the original as unverified platform knowledge. One item has since been confirmed
>   the hard way: Slack Socket Mode **load-balances events across all open connections**, so two
>   instances sharing a bot token will split incoming events non-deterministically. See §4.1 of
>   `jiuwenswarm-user-migration.md`.
>
> ### One thing the body does not cover
>
> A defect found later, not visible from static reading: the digest tool returned raw Slack `ts` values
> with no human-readable equivalent, so the model did the epoch conversion itself and misdated messages
> by four days. Fixed by adding `ts_iso_utc` per message and `earliest/latest_message_iso_utc` to
> coverage. The lesson generalises — do not hand an LLM raw epochs and expect correct dates.

---

# Slack ↔ jiuwenswarm: Connector Capability Analysis

**Date:** 2026-08-04
**Repo:** `openJiuwen-ai/jiuwenswarm`
**Branch:** `develop` (tracked; `origin/HEAD` → `origin/develop`)
**Commit:** `5a7319a4` — *fix(PromptAttachment): remove unused file hot-loading support*
**Connector history:** one commit ever — `c73eab2f [mirror] openJiuwen-ai/jiuwenswarm#1307: feat: add Slack channel support`

---

## 0. Scope and method

This document answers four questions:

1. What is **currently implemented** in the Slack ↔ jiuwenswarm connection.
2. What the **Slack API** makes possible, independent of jiuwenswarm.
3. What the **jiuwenswarm connector API** makes possible, independent of Slack.
4. What **other jiuwenswarm connectors** already implement, as proof of what is reachable.

Sections 1, 3 and 4 are derived from reading the source at the commit above; every claim carries a
`file:line` reference. Section 2 is derived from platform knowledge of the Slack API and is **not**
verifiable from this repo — treat scope names and endpoint availability as needing confirmation
against current Slack documentation before implementation.

A cross-cutting classification of each gap (Slack constraint vs. jiuwenswarm architecture vs. simply
unbuilt) is in §5. Concrete leads for an implementing agent are in §6, framed as hints rather than
specifications.

### Terminology

Two distinctions are load-bearing throughout and are easy to conflate:

| Term | Means | Does **not** mean |
|---|---|---|
| **Receives group messages** | The connector is delivered messages posted in a channel or group | That it can read anything said before it was listening |
| **Fetches backlog** | The connector calls a platform API to pull history it never received | Merely accumulating messages as they arrive |
| **Cron target** | Where a scheduled job *delivers its output* | Which channels may *create* a scheduled job |
| **Interactive formatting** | Clickable card UI (buttons, selects, modals) | Text-level markdown styling |

---

## 1. Current implementation

**Source of truth:** `jiuwenswarm/gateway/channel_manager/im_platforms/slack/slack_connect.py`
(330 lines, the entire connector).

### 1.1 Architecture

```
Slack workspace
      │  (outbound WebSocket — no public URL, no ingress required)
      ▼
AsyncSocketModeHandler ── AsyncApp ── SlackChannel(BaseChannel)
      │                                      │
      │  app_mention ─────────────┐          │
      │  message (im only) ───────┤          │
      ▼                           ▼          ▼
_handle_slack_event ──► Message(E2A) ──► RobotMessageRouter ──► Gateway ──► AgentServer
                                                      │
      chat_postMessage ◄──── SlackChannel.send ◄──────┘
```

Transport is **Socket Mode** (`slack_connect.py:96-107`), meaning the deployment needs no inbound
firewall rule, no TLS termination and no public hostname. This is a genuine operational advantage
over the Events API and is one of the few areas where the Slack connector is well-chosen.

### 1.2 Dependency and failure mode

```python
try:
    from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
    from slack_bolt.async_app import AsyncApp
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
```
— `slack_connect.py:24-32`

`slack-bolt` is an **optional** dependency. When absent, `start()` logs
`"Slack SDK not installed. Run: pip install slack-bolt"` and returns (`:80-82`). The channel is
registered but inert. There is no startup failure, so a misconfigured deployment looks healthy.

### 1.3 Configuration

`jiuwenswarm/resources/config.yaml:724-735`:

```yaml
  slack:
    # Slack Bot via Socket Mode. Tokens are created in the Slack app settings.
    bot_token:                 # xoxb-…
    app_token:                 # xapp-…  (Socket Mode)
    # Slack user IDs allowed to use the bot. Empty allows all users.
    allow_from: []
    # Channel IDs allowed to mention the bot. Empty allows all channels.
    allowed_channel_ids: []
    # Optional fallback channel for messages without request metadata.
    default_channel_id:
    reply_in_thread: true
    enabled: false
```

Mapped to `SlackChannelConfig` (`slack_connect.py:40-50`) — 7 fields, all consumed.

Wiring and hot reload live in `gateway/app_gateway.py:2331-2361`. The channel is gated by
`_is_channel_enabled(slack_conf, ["bot_token", "app_token"])`, torn down and rebuilt whenever
`channels.slack` changes in config, and cancelled on shutdown (`:2693-2699`). Hot reload therefore
works correctly; the connector's poverty is entirely in its own file.

### 1.4 Inbound capability matrix

| Capability | Status | Reference | Notes |
|---|:--:|---|---|
| Socket Mode transport | ✅ | `:96-107` | No public URL needed |
| DM (`im`) messages | ✅ | `:159-164` | Via `message` event |
| Channel `@mention` | ✅ | `:97`, `:154-157` | Via `app_mention` event |
| Channel message **without** mention | ❌ | `:162-163` | Hard-filtered, see below |
| Multi-person DM (`mpim`) | ❌ | `:162-163` | Same filter |
| Leading `<@BOT>` stripped from text | ✅ | `:196` | `_LEADING_MENTION_RE`, `count=1` |
| Bot-echo guard | ✅ | `:177` | Drops `subtype` / `bot_id` / `bot_profile` |
| Event deduplication | ⚠️ | `:253-261` | 1024-entry LRU, **in-memory only** |
| User allow-list | ✅ | `base.py:168-185` | `allow_from`; empty ⇒ everyone |
| Channel allow-list | ✅ | `:184-186` | `allowed_channel_ids`; applies to mentions only |
| Empty-message guard | ✅ | `:197-198` | Post-strip empty text is dropped |
| Thread grouping | ✅ | `:208`, `:218` | Session keyed on `root_thread_ts` |
| File / image / audio attachments | ❌ | — | Not parsed inbound |
| `message_changed` / `message_deleted` | ❌ | — | Not subscribed |
| `reaction_added` / `reaction_removed` | ❌ | — | Not subscribed |
| Slash commands | ❌ | — | Not registered |
| Shortcuts / modals / App Home | ❌ | — | Not registered |
| Channel-join / team-join events | ❌ | — | Not subscribed |

**The filter that defines the connector:**

```python
async def _handle_message_event(self, event, body) -> None:
    if str(event.get("channel_type") or "") != "im":
        return
    await self._handle_slack_event(event, body, is_dm=True)
```
— `slack_connect.py:159-164`

Every non-DM message is discarded before allow-lists, dedup or text extraction run. In channels the
bot is deaf except to `app_mention`. There is **no** `conversations.history` or
`conversations.replies` call anywhere in the connector — when mentioned mid-thread it receives only
the mention text itself and has no visibility into preceding messages.

### 1.5 Outbound capability matrix

| Capability | Status | Reference | Notes |
|---|:--:|---|---|
| Plain-text reply | ✅ | `:149` | `chat.postMessage` |
| Threaded reply | ✅ | `:146-147`, `:212-213` | Controlled by `reply_in_thread` |
| Long-message chunking | ⚠️ | `:36`, `:315-319` | 4,000 chars — **10× below Slack's 40,000 limit** |
| Streaming output | ❌ | `:132-133` | `CHAT_DELTA` explicitly returned early |
| Block Kit / rich layout | ❌ | — | `text` field only |
| Markdown fidelity | ⚠️ | — | Agent Markdown emitted raw; Slack uses *mrkdwn*, so `**bold**`, tables and fenced code render imperfectly |
| File / image upload | ❌ | — | No `files.*` usage |
| Ephemeral messages | ❌ | — | No `chat.postEphemeral` |
| Message edit / delete | ❌ | — | No `chat.update` / `chat.delete` |
| Reaction acknowledgement | ❌ | — | No `reactions.add` |
| `@`-mentioning users in replies | ❌ | — | `RoutingTarget.mention_member_ids` ignored |
| Proactive / scheduled push | ❌ | `cron/models.py:14-24` | Slack absent from `CronTargetChannel` |
| Send-failure handling | ⚠️ | `:150-152` | Logs a warning and **returns**, abandoning remaining chunks |

**Delivery-target resolution** (`:263-290`) tries four sources in order:

1. `routing_target.delivery.target_channel_id` (a `SlackDeliveryTarget`)
2. `msg.metadata["slack_channel_id"]` — captured from the inbound event
3. Parsed out of the `slack_…` session id (`:280-288`)
4. `config.default_channel_id`

Sources 1–3 are all echoes of a user-initiated conversation. Only source 4 could support unsolicited
delivery, and nothing currently invokes `send()` without an inbound trigger.

### 1.6 Session and memory model

| Context | `session_id` format | Reference |
|---|---|---|
| DM | `slack_{team}_{channel}_{user}` | `:216` |
| Channel thread | `slack_{team}_{channel}_{root_thread_ts}` | `:218` |

`root_thread_ts` falls back to the message's own `ts` when not in a thread (`:208`), so a
non-threaded mention creates a fresh session that subsequent thread replies then join.

Consequences:

- Memory **is** preserved across turns within one DM or one thread.
- Memory is **not** shared between threads in the same channel.
- The bot never ingests messages authored by others outside its own sessions.
- Slack does **not** use `SessionMap` (`message_handler.py:236-238` restricts it to
  `feishu_enterprise`); it constructs session ids inline.

### 1.7 Reliability characteristics

| Property | Behaviour |
|---|---|
| Dedup persistence | In-memory only; a restart re-admits Slack's retried events |
| Dedup capacity | 1024 events, FIFO eviction (`:256-258`) |
| Send retry | None — first exception aborts the remaining chunks (`:150-152`) |
| Rate-limit handling | None — no backoff on Slack 429 |
| Ordering | Chunks sent sequentially; no interleaving guard across concurrent sessions |
| Startup validation | Token presence only; no `auth.test` call to verify credentials |

---

## 2. What the Slack API allows

Platform capability inventory, independent of jiuwenswarm. ✅ marks what the connector uses today.
**Scope names and endpoint availability should be re-confirmed against current Slack documentation.**

### 2.1 Sending

| Method | Purpose | Typical scope | Used |
|---|---|---|:--:|
| `chat.postMessage` | Post to channel, thread, or user ID (auto-opens DM) | `chat:write` | ✅ |
| `chat.update` | Edit a posted message — **the streaming primitive** | `chat:write` | — |
| `chat.delete` | Remove a message | `chat:write` | — |
| `chat.postEphemeral` | Visible to one user only | `chat:write` | — |
| `chat.scheduleMessage` | Server-side scheduled delivery | `chat:write` | — |
| `chat.deleteScheduledMessage` | Cancel a scheduled send | `chat:write` | — |
| `chat.getPermalink` | Stable deep link to a message | `chat:write` | — |
| `chat.unfurl` | Custom link previews | `links:write` | — |

Practical limits: ~40,000 characters per `text`; 50 blocks per message; roughly 1 message/second
sustained per channel with short bursts tolerated.

### 2.2 Reading

| Method | Purpose | Typical scope |
|---|---|---|
| `conversations.history` | Channel backlog | `channels:history`, `groups:history`, `im:history`, `mpim:history` |
| `conversations.replies` | Full thread | same family |
| `conversations.list` | Enumerate channels | `channels:read` |
| `conversations.info` | Channel metadata | `channels:read` |
| `conversations.members` | Membership | `channels:read` |
| `conversations.open` | Open/resolve a DM channel by user ID | `im:write` |
| `conversations.join` | Bot self-joins a public channel | `channels:join` |
| `search.messages` | Workspace search | **user token only** — unavailable to bots |

`conversations.history` and `.replies` are the two calls that would close the biggest functional gap.

### 2.3 Events

| Event | Fires on | jiuwenswarm |
|---|---|:--:|
| `app_mention` | Bot is @-mentioned | ✅ |
| `message.im` | DM to the bot | ✅ |
| `message.channels` | Any message in a public channel the bot is in | ❌ |
| `message.groups` | Private channel | ❌ |
| `message.mpim` | Group DM | ❌ |
| `message_changed` (subtype) | Edit | ❌ |
| `message_deleted` (subtype) | Deletion | ❌ |
| `reaction_added` / `reaction_removed` | Emoji reaction | ❌ |
| `file_shared` / `file_created` | File upload | ❌ |
| `member_joined_channel` / `member_left_channel` | Membership change | ❌ |
| `team_join` | New workspace member | ❌ |
| `app_home_opened` | User opens the App Home tab | ❌ |
| `channel_created` / `channel_rename` / `channel_archive` | Channel lifecycle | ❌ |
| `assistant_thread_started` | AI-app assistant thread opened | ❌ |
| `tokens_revoked` / `app_uninstalled` | Install lifecycle | ❌ |

The bot must be a member of a channel to receive `message.channels`. That is the only true Slack-side
precondition for passive reading, and it is trivially satisfiable via `conversations.join` or by
inviting the app.

### 2.4 Interactivity and UI

| Surface | Description |
|---|---|
| **Block Kit** | Structured layout: sections, dividers, context, images, rich text, and interactive elements |
| **Interactive components** | Buttons, static/external/multi selects, overflow menus, date/time pickers, checkboxes, radio buttons |
| **Modals** | `views.open`, `views.push`, `views.update` — multi-step dialogs |
| **App Home** | `views.publish` — a persistent per-user tab, ideal for agent status or config |
| **Slash commands** | `/command` registered in app settings, delivered over Socket Mode |
| **Shortcuts** | Global (composer) and message-level entry points |
| **Link unfurling** | Custom previews for owned domains |
| **Workflow steps** | Custom steps usable inside Slack Workflow Builder |

An agent product would plausibly want at minimum: buttons for plan approval (mapping directly onto
jiuwenswarm's `PLAN_APPROVAL_REQUIRED` event), a modal for `CHAT_ASK_USER_QUESTION`, and App Home for
session listing.

### 2.5 AI-app / assistant surface

Slack's Agents & AI-apps surface provides purpose-built affordances for exactly this class of
integration — assistant threads with a status/"thinking" indicator, suggested prompts, and a
dedicated split-view container. jiuwenswarm uses none of it. This is the most product-relevant gap
after passive reading, and it should be verified against current Slack docs since this surface has
evolved quickly.

### 2.6 Files, reactions, users, admin

| Area | Methods |
|---|---|
| Files (v2 upload) | `files.getUploadURLExternal` → `files.completeUploadExternal`; `files.info`, `files.list`, `files.delete` |
| Reactions | `reactions.add`, `reactions.remove`, `reactions.get`, `reactions.list` |
| Users | `users.list`, `users.info`, `users.lookupByEmail`, `users.conversations`, `users.profile.get` |
| User groups | `usergroups.list`, `usergroups.users.list` |
| Pins / bookmarks | `pins.add`, `pins.remove`, `bookmarks.add` |
| Canvases | Create and update canvas documents |
| Auth | `auth.test` — token validation and bot identity discovery |
| Admin (Enterprise Grid) | `admin.conversations.*`, `admin.users.*` |
| Discovery API | Org-wide compliance export; separate entitlement |

`auth.test` is worth noting: it would let the connector self-discover its own bot user ID rather than
relying on the regex strip at `:196`, and would surface bad tokens at startup instead of at first
message.

---

## 3. The jiuwenswarm connector API

### 3.1 `BaseChannel` — the contract

`jiuwenswarm/gateway/channel_manager/base.py:114-211`. Five members:

| Member | Kind | Contract |
|---|---|---|
| `start()` | abstract | Connect, listen, forward inbound via `_handle_message` |
| `stop()` | abstract | Release resources |
| `send(msg, *, routing_target)` | **concrete default** | Base implementation logs a warning and **drops the message** (`:162-166`) |
| `is_allowed(sender_id)` | concrete | Allow-list check; supports composite `a\|b` ids (`:181-184`) |
| `_handle_message(chat_id, content, metadata)` | concrete | Builds a `Message` with `session_id = str(chat_id)` |

`send()` not being abstract is a notable design weakness: a partially implemented connector silently
swallows every reply instead of failing at import. Slack overrides it, so this does not affect Slack —
but it explains why connector quality varies so widely without anything breaking loudly.

`ChannelType` (`base.py:21-35`) enumerates 13 channels: `acp`, `web`, `feishu`, `xiaoyi`, `dingtalk`,
`telegram`, `discord`, `slack`, `whatsapp`, `wecom`, `wechat`, `ssh`, `tui`.

### 3.2 `RobotMessageRouter` — the bus

`base.py:48-111`. Two `asyncio.Queue`s (inbound `_user_messages`, outbound `_robot_messages`) plus a
per-channel subscription registry. `dispatch_robot_messages()` (`:82-97`) polls with a 1-second
timeout and fans each outbound message to callbacks registered for `msg.channel_id`. Exceptions in a
callback are logged and swallowed (`:94-95`) — a failing channel cannot stall the bus, but it also
cannot signal backpressure.

### 3.3 Event vocabulary available to any connector

`jiuwenswarm/common/schema/message.py:219-249` — `EventType` has 30 members:

| Group | Events |
|---|---|
| Connection | `connection.ack`, `hello` |
| Streaming | `chat.delta`, `chat.reasoning`, `chat.final`, `chat.retract` |
| Media | `chat.media`, `chat.file` |
| Tools | `chat.tool_call`, `chat.tool_update`, `chat.tool_result` |
| Progress | `todo.updated`, `chat.processing_status`, `chat.subtask_update`, `context.usage` |
| Interaction | `chat.ask_user_question`, `plan.approval_required` |
| Team | `team.member`, `team.task` |
| Goals | `goal.snapshot`, `goal.updated` |
| Meta | `chat.usage_metadata`, `chat.usage_summary`, `chat.symphony_status`, `chat.evolution_status`, `chat.session_result`, `chat.interrupt_result` |
| Errors | `chat.error`, `execution.error`, `runtime.accepted` |

**The Slack connector renders one of these thirty** (`chat.final`, implicitly, by dropping
`chat.delta` and extracting text from whatever else arrives). Each unrendered event is a capability
the agent already produces and the Slack user never sees.

Particularly costly omissions:
- `plan.approval_required` — maps naturally onto a Block Kit button pair
- `chat.ask_user_question` — maps onto a modal or a threaded prompt
- `todo.updated` / `chat.subtask_update` — maps onto a periodically `chat.update`-ed status message
- `chat.file` / `chat.media` — maps onto `files.completeUploadExternal`

### 3.4 Routing and delivery

`RoutingTarget` (`gateway/routing/session_sharing.py:93-115`):

| Field | Meaning |
|---|---|
| `intent` | `'godview'` or `'mention'` |
| `member_names` | Logical recipient seats |
| `speaker` | Originating member |
| `mention_all` | Broadcast flag |
| `routing_keys` | `list[RoutingKey]` — the 5-dimensional address |
| `mention_member_ids` | **Physical @-mention user ids** |
| `delivery` | A `DeliveryTarget` subclass |

`SlackDeliveryTarget` (`gateway/routing/keys.py:265-279`) carries `target_channel_id`, `thread_ts`,
`chat_type` and `physical_user_id`, and is constructed by `make_delivery_target` (`:375-381`). The
plumbing for addressed, @-mentioning replies therefore exists end-to-end; `SlackChannel.send()`
simply ignores `mention_member_ids`.

### 3.5 Scheduled and proactive delivery

`gateway/cron/models.py:14-24`:

```python
class CronTargetChannel(str, Enum):
    WEB = "web"; TUI = "tui"; FEISHU = "feishu"; WHATSAPP = "whatsapp"
    WECOM = "wecom"; XIAOYI = "xiaoyi"; WECHAT = "wechat"; DINGTALK = "dingtalk"
```

Slack, Telegram and Discord are **absent**.

`CronTargetChannel` is **not** the list of channels that may *create* a job — it is the list of
channels a job may *deliver its output to*. Job creation is available to the agent on every channel,
via the `cron` tool family (`agents/harness/common/tools/cron/`). The two are decoupled, and that
decoupling is where Slack breaks.

**What happens when a Slack user asks for a scheduled task.** The tool bridge derives the delivery
target from the request context when none is given explicitly:

```python
targets = str(
    delivery.get("channel")
    or data.get("targets")
    or (context.channel_id if context else "")   # ← "slack"
    or CronTargetChannel.WEB.value
).strip() or CronTargetChannel.WEB.value
```
— `cron/cron_runtime.py:315-319`

`targets` becomes `"slack"`, which then reaches the controller:

```python
if not is_valid_target_channel_id(raw_s):
    raise ValueError(
        "targets must be one of tui/web/feishu/dingtalk/whatsapp/wecom/xiaoyi/wechat"
        " or feishu_enterprise:<app_id>"
    )
```
— `cron/controller.py:82-93`

So creating a scheduled job from a Slack conversation **raises**, with an error message that lists
the valid channels and omits Slack. The agent surfaces that failure to the user. It does not silently
misroute at creation time.

**Where silent coercion does occur** is the *deserialization* path — `CronJob.from_dict`
(`models.py:372`) calls `_normalize_targets_str` (`:64-66`), which falls back to `web` on an
unrecognized value rather than raising. That governs jobs loaded from `cron_jobs.json`, so a job
persisted with a target that later leaves the enum reappears pointing at the web client. Defensible
for migration tolerance, but it should log.

Consequence either way: scheduled tasks, and the proactive-recommendation engine that rides the same
`proactive.tick` push path, cannot deliver to Slack.

### 3.6 Shared infrastructure a connector may opt into

| Facility | Location | Currently used by |
|---|---|---|
| `MessageStore` — group history fetch + persisted memory | `im_platforms/platform_adapter/message.py` | Feishu, WeCom |
| `SessionMap` — durable routing map | `gateway/routing/session_map.py` | `feishu_enterprise` only |
| Hot config reload | `app_gateway.py:2331-2361` (Slack block) | All channels ✅ |
| Allow-list | `base.py:168` | All channels ✅ |
| File services | per-platform (`*_file_service.py`) | Feishu, WeCom, DingTalk |
| Streaming card / edit | per-platform | Feishu, Xiaoyi, WeCom, WeChat, WhatsApp |

---

## 4. What other connectors implement

### 4.1 Feature matrix

"Reads groups" = receives messages in group/channel contexts at all. Whether that includes *backlog
fetching* is a separate column, because only one connector does it.

"Formatting" distinguishes three levels: **interactive** (clickable card UI), **markdown** (text-level
styling only), **plain** (raw text).

| Connector | LOC | Group msgs | Backlog fetch | Streaming | Files | Formatting | Reaction ack | Cron target |
|---|--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Feishu | 3,616 | ✅ | ✅ **`conversations` history** | ✅ card | ✅ (720) | **interactive** | — | ✅ |
| Xiaoyi | 2,049 | ✅ | — | ✅ | ✅ | plain | — | ✅ |
| WeCom | 1,828 | ✅ | ✅ via `MessageStore` | ✅ | ✅ (298) | markdown | — | ✅ |
| WeChat | 1,406 | — | — | ✅ | — | plain | — | ✅ |
| DingTalk | 1,152 | ✅ | — | — | ✅ (475) | plain out | — | ✅ |
| WhatsApp | 501 | — | — | ✅ | — | plain | — | ✅ |
| Telegram | 404 | ✅ **4-mode switch** | — | — | — | markdown | ✅ 👀 | ❌ |
| **Slack** | **330** | mention only | ❌ | ❌ | ❌ | plain | ❌ | ❌ |
| Discord | 272 | ✅ guild filter | — | — | — | plain | ✅ 👀 / 🚫 | ❌ |

Evidence for the formatting column: Feishu posts `msg_type="interactive"` with `card_json`
(`feishu_connect.py:1691`, `feishu_streaming_card.py:62`); WeCom posts
`{"msgtype": "markdown", ...}` (`wecom_connect.py:270`); Telegram sets
`parse_mode: Markdown|HTML` (`telegram_connect.py:46`, `:184`). DingTalk parses an inbound `msgtype`
(`:166`) but its outbound path emits plain text (`:493-494`). Xiaoyi's markdown/html strings are MIME
types for media attachments (`xiaoyi_utils/media.py:336-337`), not message formatting.

**Only Feishu has genuine interactive UI.** Two connectors have text-level markdown. Six, including
Slack, emit plain text.

Total connector code: 14,105 lines. The four Chinese-platform connectors account for ~9,900 of them.
Slack, Discord and Telegram together account for ~1,000 — and are precisely the three excluded from
cron delivery. The correlation is not coincidental; it reflects where the product's users are.

### 4.2 Reference implementation: Telegram's group-chat mode

`im_platforms/telegram/telegram_connect.py:295-335`, config field at `:47`
(`group_chat_mode: str = "mention"`):

```python
is_group_chat = update.effective_chat.type in ["group", "supergroup"]
if is_group_chat:
    group_mode = self.config.group_chat_mode
    if group_mode == "off":
        return
    if group_mode == "mention":
        bot_username = context.bot.username
        mention_text = f"@{bot_username}"
        if mention_text not in text:
            return
        text = text.replace(mention_text, "").strip()
    elif group_mode == "reply":
        if not update.message.reply_to_message:
            return
    # "all" falls through — responds to everything
```

Four modes: `all`, `mention`, `reply`, `off`. This is exactly the policy Slack needs, already written
and already wired through config hot-reload (`app_gateway.py:2296`). Porting it is a
structural translation, not a design exercise.

Note the bot-identity handling: Telegram queries `context.bot.username` at runtime rather than
regex-stripping. Slack's equivalent is `auth.test`.

### 4.3 Reference implementation: Feishu's history fetch

`im_platforms/platform_adapter/message.py`, class `MessageStore` (`:43`):

| Method | Line | Role |
|---|--:|---|
| `load_memory(chat_id)` | 102 | Read persisted group memory |
| `_save_memory(memory, chat_id)` | 143 | Persist |
| `_parse_history_message_content(item)` | 169 | Normalize platform payload → text |
| `_fetch_history_from_feishu(chat_id, start_time)` | 230 | **Platform-specific fetch** |
| `_get_or_fetch_history(chat_id)` | 307 | Cache-or-fetch, incremental since last timestamp |
| `add_message_to_memory(chat_id, message)` | 365 | Append live message |

Only `_fetch_history_from_feishu` is platform-bound. The caching, incremental-fetch and persistence
logic is generic. A `_fetch_history_from_slack` wrapping `conversations.replies` would reuse the rest
directly. `MessageStore` is already shared by two connectors (`feishu_im_adapter.py:10`,
`wecom_connect.py:22`), so a third consumer is an anticipated use.

### 4.4 Reference implementation: reaction acknowledgement

Discord (`discord_connect.py:175-185`, `:256-258`):

```python
@staticmethod
async def _add_reaction_emoji(message: Any, emoji: str = "👀") -> Exception | None:
    try:
        await message.add_reaction(emoji)
```

👀 on accept, 🚫 on rejection. Telegram does the same via `set_reaction("👀")`
(`telegram_connect.py:348`). Both give the user immediate confirmation that the bot saw the message —
valuable precisely because neither streams. Slack has `reactions.add` and does not use it.

---

## 5. Gap classification

Every gap identified above, sorted by root cause.

### 5.1 Genuine Slack platform constraints

| Gap | Nature | Workaround |
|---|---|---|
| No native streaming | Slack has no streaming primitive | Emulate with throttled `chat.update` at ~1/sec; this is what mature Slack AI bots do |
| `search.messages` unavailable to bots | User-token-only endpoint | Use `conversations.history` per channel, or require a user token |
| Bot must join a channel to read it | Membership precondition | `conversations.join`, or invite the app |

That is the complete list. Everything else below is self-inflicted.

### 5.2 jiuwenswarm architectural decisions

| Gap | Assessment |
|---|---|
| `CronTargetChannel` is a closed enum | Reasonable, but omits three connectors — job *creation* from Slack therefore raises |
| `from_dict` coerces unknown target → `web` without logging | Minor defect on the persistence path; the strict validator (`controller.py:82`) guards creation correctly |
| Dedup cache in-memory only | House-wide pattern; a restart can double-answer a retried event |
| `BaseChannel.send()` concrete, not abstract | Lets incomplete connectors fail silently |
| `SessionMap` restricted to `feishu_enterprise` | Slack reimplements session-id construction inline |
| No per-channel rate-limit / retry policy in the bus | Each connector must handle 429 itself; Slack handles none |

### 5.3 Simply unimplemented (no obstacle)

Passive channel reading · proactive DMs · Block Kit · file upload/download · reactions · message
edit/delete · ephemeral messages · slash commands · shortcuts · modals · App Home · assistant-thread
surface · `auth.test` identity discovery · @-mention in replies · 29 of 30 `EventType` renderings ·
the 4,000-char cap.

---

## 6. Implementation hints

> **These are hints, not specifications.**
>
> Every item below was located by reading the source at commit `5a7319a4` and is accurate as of that
> commit. They are starting points that save discovery time — not a complete change list. An agent
> implementing any of them should expect to find **additional call sites, tests, config surfaces and
> edge cases not named here**, and should treat a mismatch between this document and the code as
> evidence the code moved, not as a reason to force the described change.
>
> Line numbers drift. Prefer the symbol names when locating code.
>
> Effort figures are rough production-line counts excluding tests.

### 6.1 Hint index

| # | Hint | Effort | Tier | Confidence |
|--:|---|---|---|---|
| H1 | Add Slack to `CronTargetChannel` | ~20 | 1 | High — enum + one branch |
| H2 | Log the cron-target coercion on load | ~3 | 1 | High |
| H3 | Raise `_MAX_SLACK_TEXT_LENGTH` | 1 | 1 | High |
| H4 | Reaction acknowledgement | ~15 | 1 | High — two connectors do it |
| H5 | `auth.test` at startup | ~10 | 1 | High |
| H6 | Passive channel reading | ~40 | 2 | High — Telegram is a direct model |
| H7 | Thread/channel history ingestion | ~60 | 2 | Medium — `MessageStore` reuse untested for Slack |
| H8 | Streaming via throttled `chat.update` | ~60 | 2 | Medium — rate-limit behaviour needs live testing |
| H9 | Block Kit rendering | large | 3 | Low — no in-repo precedent outside Feishu |
| H10 | File exchange | large | 3 | Medium |
| H11 | Interactive approvals | large | 3 | Low |
| H12 | Assistant-thread surface | large | 3 | Low — verify current Slack API first |
| H13 | Durable dedup | ~30 | 3 | Medium |

---

### H1 — Add Slack as a cron / proactive target

**Why it matters.** Single highest-leverage change. Unblocks scheduled jobs, proactive
recommendations, unsolicited DMs, *and* job creation from Slack, which today raises at
`controller.py:88` because `"slack"` fails `is_valid_target_channel_id`.

**Where.**
- `gateway/cron/models.py:14-24` — add `SLACK = "slack"` to `CronTargetChannel`.
- `gateway/cron/controller.py:82-93` — the error string enumerates valid channels literally; update it
  or it will lie.
- `gateway/cron/scheduler.py:~1238` — add a Slack branch beside the DingTalk one, populating
  `metadata["slack_channel_id"]` (and optionally `slack_thread_ts`).

**Watch out.**
- The scheduler's per-channel metadata block reads "most recent inbound identity" from `config.yaml`
  (`last_sender_id`, `last_conversation_id` for DingTalk). Slack has no equivalent persisted field
  today — either add one on inbound, or fall back to `default_channel_id`.
- `send()` needs no change: `chat.postMessage` accepts a user ID as `channel` and opens the DM.
- Grep for other places the enum is enumerated — `controller.py:457` and `:559` embed
  `[e.value for e in CronTargetChannel]` in a JSON schema, so those pick it up automatically, but
  there may be prompt text or docs listing channels by hand.

**Verify.** Create a job from a Slack DM; confirm it persists to `~/.jiuwenswarm/agent/cron_jobs.json`
with `targets: "slack"` and fires into the originating conversation.

---

### H2 — Log the cron-target coercion on load

**Where.** `gateway/cron/models.py:64-66`, `_normalize_targets_str`.

Unknown persisted targets are silently rewritten to `web`. Add a `logger.warning` naming the original
value. Independent of any Slack work; affects every channel outside the enum.

**Note.** Do *not* make this raise — it is the deserialization path and tolerating unknown values is
deliberate migration behaviour. The strict validator already guards creation at `controller.py:82`.

---

### H3 — Raise the outbound chunk limit

**Where.** `slack_connect.py:36`, `_MAX_SLACK_TEXT_LENGTH = 4000`.

Slack's `chat.postMessage` accepts ~40,000 characters. 4,000 fragments long answers ten times more
than necessary. Raise to ~38,000 for margin.

**Improvement worth folding in.** `_split_text` (`:315-319`) slices blindly and will cut mid-word and
mid-code-fence. Splitting on paragraph, then line, then hard-slice would be a strict improvement.

---

### H4 — Reaction acknowledgement

**Where.** `slack_connect.py:_handle_slack_event`, after the allow-list check (`:182`).

Add `reactions.add` — 👀 on accept, 🚫 on allow-list rejection. Direct model:
`discord_connect.py:175-185` and `:256-258`; Telegram does the same at `:348`.

**Watch out.** Needs the `reactions:write` scope. Failures must be non-fatal — Discord's helper
returns the exception rather than raising, which is the pattern to copy. Highest
perceived-responsiveness gain per line in this document, precisely because streaming is absent.

---

### H5 — `auth.test` at startup

**Where.** `slack_connect.py:start()`, after the `AsyncApp` is constructed (`:96`).

Call `auth.test`, log the bot identity, cache the bot user ID.

**Two problems it fixes.**
1. A bad or revoked token currently surfaces only when the first message fails. `start()` validates
   token *presence* but never *validity* (`:86-91`).
2. `_LEADING_MENTION_RE` (`:35`, applied at `:196`) strips *any* leading `<@…>`, not specifically the
   bot's. A message beginning with a mention of another user loses it. With the real bot ID cached,
   strip precisely.

---

### H6 — Passive channel reading

**Why it matters.** Prerequisite for anything channel-aware. Currently every non-DM message is
discarded at `slack_connect.py:162-163`.

**Direct model.** `telegram_connect.py:295-335` — a four-mode switch (`all | mention | reply | off`)
with the config field at `:47` and hot-reload wiring at `app_gateway.py:2296`. Port the structure.

**Where.**
- `SlackChannelConfig` (`slack_connect.py:40-50`) — add `group_chat_mode: str = "mention"`.
- `_handle_message_event` (`:159-164`) — replace the `!= "im"` return with the mode switch.
- `app_gateway.py:2331-2361` — thread the new field through the config→dataclass mapping.
- `resources/config.yaml:724-735` — document the field and its default.
- Slack app manifest — subscribe to `message.channels`, plus `message.groups` for private channels.
- Scopes — `channels:history`, and `groups:history` if private channels are in scope.

**Watch out.**
- `all` mode makes the bot answer *every* message in *every* channel it belongs to. Default must stay
  `mention`. Pair with `allowed_channel_ids`, which today only gates mentions (`:184-186`).
- Slack's `reply` equivalent is `thread_ts` pointing at a message the bot authored — not a direct
  analogue of Telegram's `reply_to_message`. Requires tracking the bot's own message timestamps, or
  approximating via "is in a thread the bot has posted in".
- Session-id derivation (`:215-218`) assumes mention-initiated threads. Under `all` mode every thread
  becomes a session; consider the volume implications on session storage.
- The distributed config templates (`config.team.distributed.{leader,teammate}.yaml`) carry their own
  channel blocks — check whether Slack appears there.

---

### H7 — Thread and channel history ingestion

**Why it matters.** This, not H6, is what makes "@bot summarize this thread/channel" work. H6 only
delivers messages arriving *after* the bot starts listening; summarization needs backlog.

**Direct model.** `im_platforms/platform_adapter/message.py`, class `MessageStore` (`:43`). Only
`_fetch_history_from_feishu` (`:230`) is platform-bound. Caching, incremental fetch since last
timestamp (`_get_or_fetch_history`, `:307`), parsing (`:169`) and persistence (`:143`) are generic and
already shared by two connectors (`feishu_im_adapter.py:10`, `wecom_connect.py:22`).

**Where.** Add `_fetch_history_from_slack(chat_id, start_time)` calling `conversations.replies`
(thread scope) or `conversations.history` (channel scope), normalizing into the same dict shape
`_parse_history_message_content` expects. Instantiate a `MessageStore` in `SlackChannel` and populate
on first mention in an unseen thread.

**Watch out.**
- `MessageStore.get_user_name_by_open_id` (`:73`) is Feishu-shaped. Slack needs `users.info` with
  caching, or the store needs a resolver hook.
- Pagination — `conversations.replies` returns cursors; a long thread needs looping.
- Volume — a busy channel's backlog can exceed the model's context. Cap by count or age and say so in
  the prompt, rather than silently truncating.
- Privacy — the bot ingesting historical messages authored by non-participants is a policy question
  for the deploying workspace, not just a technical one. Worth a config flag and a note in the docs.

---

### H8 — Streaming via throttled `chat.update`

**Where.** `slack_connect.py:132-133` currently drops `CHAT_DELTA` outright.

**Shape.** On first delta, post a placeholder and retain its `ts`. Buffer deltas; `chat.update` at
most once per second. Finalize on `CHAT_FINAL`. Conceptually mirrors `feishu_streaming_card.py`
(263 lines) but edit-based rather than card-based.

**Watch out.**
- Slack sustains roughly one message operation per second per channel. Multiple concurrent sessions in
  one channel share that budget — the throttle must be per-channel, not per-session.
- Handle `message_not_found` if a user deletes the placeholder mid-stream.
- Consider whether streaming is even desirable in a shared channel; it produces visible churn. A
  reasonable default is streaming in DMs, single final message in channels.

---

### H9–H13 — Larger items

| # | Item | Notes |
|--:|---|---|
| H9 | **Block Kit rendering** | Convert agent Markdown → blocks; `todo.updated` → checklist, `chat.tool_call` → context lines. No in-repo precedent outside Feishu's card builder, so expect original design work. Slack renders *mrkdwn*, not CommonMark — tables and fenced code need explicit handling. |
| H10 | **File exchange** | Inbound via `file_shared` + authenticated download; outbound via `files.getUploadURLExternal` → `files.completeUploadExternal`. References: `feishu_file_service.py` (720), `dingtalk_file_service.py` (475), `wecom_file_service.py` (298). Maps to the `chat.file` / `chat.media` events already emitted. |
| H11 | **Interactive approvals** | Buttons for `PLAN_APPROVAL_REQUIRED`, modal for `CHAT_ASK_USER_QUESTION`. Requires an interactivity payload handler, absent today — Bolt provides `app.action()` / `app.view()`. |
| H12 | **Assistant-thread surface** | Slack's AI-app container, status indicator, suggested prompts. **Verify the current API shape before committing** — this surface has changed quickly and §2.5 is unverified. |
| H13 | **Durable dedup** | Persist seen event ids so a restart does not re-answer Slack's retried events. Local precedent for cross-process durable state: `CronJobStore` with portalocker at `cron/store.py:117-147`. |

---

### 6.2 Cross-cutting notes for the implementer

- **Nothing here requires changes outside `jiuwenswarm`.** `agent-core` and the other nine repos hold
  no channel code (§8.3).
- **`send()` is not abstract** (`base.py:150-166`) — the base implementation logs and drops. If a new
  code path forgets to override or returns early, messages vanish silently. Prefer explicit logging
  over silent returns in any new branch.
- **Existing tests.** `tests/unit_tests/channel/test_slack_channel.py` exists and covers
  `SlackDeliveryTarget` construction and `make_delivery_target`. Extend it rather than starting fresh.
- **Config surfaces multiply.** A new `SlackChannelConfig` field must be threaded through
  `resources/config.yaml`, `app_gateway.py`'s mapping block, and possibly the distributed templates
  and the web settings panel (`app_web_handlers.py`). Grep for an existing field such as
  `reply_in_thread` to find every place it must appear.
- **Scope changes require workspace-admin reinstall.** Batch scope additions (H4, H6, H7 all add
  scopes) into as few app-manifest revisions as possible.

---

## 7. Risks and caveats

| Risk | Detail |
|---|---|
| `all` group mode is loud | The bot answers everything in every joined channel. Ship with `mention` default. |
| Scope escalation | Passive reading needs `channels:history`; workspace admins may resist. Prepare the justification. |
| Rate limits | `chat.update` streaming plus multiple concurrent sessions can hit per-channel limits. Needs a token-bucket per channel. |
| Restart double-answer | Until dedup is durable, restarts during Slack's retry window can duplicate replies. |
| Markdown mismatch | Agent output is CommonMark; Slack renders *mrkdwn*. Tables and fenced blocks degrade. |
| Fork drift | All of this is local modification to a submodule; upstream has touched the Slack connector exactly once. Rebasing is cheap now, less so later. |
| Section 2 is unverified | Slack API details here come from platform knowledge, not from this repo. Confirm scopes and endpoint names against current docs before implementing. |

---

## 8. Appendix

### 8.1 File index

| Path | Lines | Role |
|---|--:|---|
| `im_platforms/slack/slack_connect.py` | 330 | The entire Slack connector |
| `channel_manager/base.py` | 211 | `BaseChannel`, `RobotMessageRouter`, `ChannelType` |
| `common/schema/message.py` | — | `Message`, `EventType` (`:219-249`) |
| `gateway/routing/keys.py` | — | `RoutingKey`, `SlackDeliveryTarget` (`:265`), `make_delivery_target` (`:314`) |
| `gateway/routing/session_sharing.py` | — | `RoutingTarget` (`:93`) |
| `gateway/cron/models.py` | — | `CronTargetChannel` (`:14`), target normalization (`:48-66`) |
| `gateway/cron/scheduler.py` | — | Push routing (`:1205-1260`) |
| `gateway/app_gateway.py` | — | Slack registration + hot reload (`:2331-2361`) |
| `im_platforms/platform_adapter/message.py` | 384 | `MessageStore` — history + memory |
| `im_platforms/telegram/telegram_connect.py` | 404 | `group_chat_mode` reference (`:295-335`) |
| `im_platforms/discord/discord_connect.py` | 272 | Reaction-ack reference (`:256-258`) |
| `resources/config.yaml` | — | `channels.slack` block (`:724-735`) |

### 8.2 Verification commands

```bash
cd /home/ai/code/jiuwen/jiuwenswarm

# Confirm no history fetching anywhere
grep -rn "conversations_history\|conversations_replies\|channels:history" jiuwenswarm/

# Confirm Slack is absent from cron targets
grep -n "class CronTargetChannel" -A 12 jiuwenswarm/gateway/cron/models.py

# Connector size comparison
wc -l jiuwenswarm/gateway/channel_manager/im_platforms/*/*.py | sort -n

# The reference implementation to port
sed -n '295,335p' jiuwenswarm/gateway/channel_manager/im_platforms/telegram/telegram_connect.py
```

### 8.3 Related repositories checked

`agent-core` (the `openjiuwen` SDK) contains no channel or IM code — connectors are wholly a
jiuwenswarm concern. `agent-protocol`, `agent-memory`, `agent-tools`, `skillhub`, `agent-runtime` and
the two Java repos are likewise unrelated to channel delivery. No cross-repo work is required for any
item in §6.
