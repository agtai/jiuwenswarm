# Slack event metadata: how it flows, and what it would take to expose it

Investigation only; no source was changed. Every behavioural claim cites `file:line` against
`local/deployed` — jiuwenswarm `1a74ee462`, agent-core (openjiuwen) `80a53799`. Statements that are
inference rather than read off the code are marked **(inferred)**.

Paths are relative to each repo root.

---

## 1. The mechanism first: dumped, or queryable?

**Both mechanisms exist and are in daily use. Slack metadata is plumbed into neither.** There is
also a third, which the question did not anticipate and which turns out to be the cheapest place
to fix this.

### 1.1 Three model-visible surfaces, none carrying Slack metadata

**(a) The prompt-attachment block — re-rendered on every model call.**
`openjiuwen/harness/prompts/prompt_attachment_manager.py:552` registers `make_window_mutator` as a
ContextEngine *final-window mutator*, wired in at `openjiuwen/core/single_agent/react_agent.py:956-964`.
On each model call it re-collects the session's attachments (`:464`), renders them into one
`<system-reminder>` block (`:484-529`) and splices that in as a `UserMessage` (`:533-549`).
Anything here is paid **every turn, used or not**, but only ever as **one** copy.

The host writes exactly two sections, both from
`jiuwenswarm/agents/harness/common/rails/runtime_prompt_rail.py`:

| Section | Line | Contents |
|---|---|---|
| `runtime.setting` | `:290-296` | model, available models, mode, language, **channel** |
| `git_status` | `:390-396` | branch, main branch, git user, status, recent commits |

**(b) The system prompt.** Same rail adds a static `env` section (`:361-365`) with platform, shell,
encoding rules, **current UTC time** (`:316-317`) and again the channel.

In both, "channel" is the *channel kind* — `slack`, `web`, `acp` — resolved at
`runtime_prompt_rail.py:270`. Not the conversation. The model is told it is on Slack and nothing
more.

**(c) The user-turn JSON envelope — the surface the question did not anticipate.**
The user message is not the user's text. `UserTurn.render()`
(`jiuwenswarm/server/runtime/agent_adapter/user_turn.py:67-106`) emits
`_interaction_prefix() + _lead_in(...) + json.dumps(envelope)`. The envelope (`:110-131`) is:

| Field | Line | Value |
|---|---|---|
| `source` | `:113` | the channel kind (`slack`) |
| `timezone` | `:114` | hardcoded `"Asia/Shanghai"` |
| `timestamp` | `:111,115` | **`datetime.now(UTC+8)` at render time** |
| `preferred_response_language` | `:116` | — |
| `content` | `:117` | the user's text |
| `type` | `:118` | `"user input"` |
| `files_updated_by_user` | `:123` | — |
| `skills_to_use`, `trusted_dirs` | `:127,129` | conditional |
| **`chat_type`, `sender`** | `:129` → `_sender_fields()` `:147-160` | **read from request metadata** |

`_sender_fields()` is already a metadata-to-model bridge. It reads
`metadata["chat_type"] or metadata["im_chat_type"]` (`:152-156`) and `metadata["sender_name"]`
(`:157-159`). The `UserTurn` is constructed with the full request metadata at
`jiuwenswarm/server/runtime/agent_adapter/interface.py:1118-1126`.

For Slack this yields nothing on the ordinary path — the connector sets neither key. In
group-digital-avatar mode it sets `chat_type = "group"` (`slack_connect.py:2714-2715`), so
`chat_type` and only `chat_type` reaches the model.

### 1.2 This is why the model fabricated a timestamp

Two facts, both read from code:

- The model is handed a field literally named **`timestamp`** inside its own user turn
  (`user_turn.py:115`), whose value is the adapter's wall clock in UTC+8 at render time — not when
  the Slack message was posted.
- No Slack timestamp reaches the model by any route.

A model asked for "the Slack message timestamp" has exactly one plausibly-named candidate in
context, and it is wrong. **(inferred as the causal chain; both halves are read from code.)**

This is a provenance defect in its own right, independent of the metadata question: the envelope
advertises a `timestamp` for a user message that is really a processing time, and pairs it with a
hardcoded `Asia/Shanghai` label.

The codebase already knows this failure mode. `slack_history.py:609-613` returns both `ts` and
`ts_iso_utc` per history record, with the comment:

> *"ts is a Slack message identifier that happens to look like a Unix epoch. Models read it as a
> date and get it wrong, so state the date explicitly rather than making them do the arithmetic."*

### 1.3 Query-on-demand exists, and is the live precedent

Request metadata is bound into ContextVars for the turn:

- declared at `jiuwenswarm/server/runtime/agent_adapter/interface_deep.py:355-376`
- bound by `_bind_runtime_cron_context` (`:5781-5842`), which copies `request.metadata` verbatim
  (`:5796`) and adds `request_id`, `project_dir`, session-derived `project_id`/`work_mode`
- called around the turn at `:8825` and `:9409`
- surfaced through the `_RuntimeCronToolContext` proxy (`:1035-1088`), which keeps a remembered
  fallback (`:8833`, `:9417`) so it survives the DeepAgent worker boundary

`SlackHistoryToolkit` is built against that proxy rather than against tool arguments
(`interface_deep.py:6163-6166`), through a provider (`:6188-6192`) that delegates to
`_filter_slack_history_request_metadata` (`:395-407`). That gate **fails closed** — it returns `{}`
unless the channel is literally `slack` *and* `slack_channel_id` is non-empty *and*
`slack_history_digest_allowed is True` — and otherwise returns `dict(metadata)`, the **entire**
dict, unfiltered.

So the machinery to answer *"which Slack message am I replying to?"* already exists, is already
security-reviewed, and already hands `slack_message_ts` to a toolkit that never reads it.

`get_runtime_tool_session_id()` (`interface_deep.py:390-392`), flagged as the possible precedent,
is **not** one: grepping both repos and `local_skills/` returns only its definition. It is unused.

### 1.4 A third consumer: permissions

`setup_permission_context`
(`jiuwenswarm/agents/harness/common/rails/permissions/owner_scopes.py:61-88`), called at
`interface_deep.py:8836`, lifts `avatar_mode`, `principal_user_id`, `triggering_user_id`,
`group_digital_avatar`, `enable_memory`, `avatar_principal_name` into a second ContextVar
`TOOL_PERMISSION_CONTEXT` (`:55-58`) used to gate tool calls. Host-side only.

### 1.5 The one existing leak of Slack metadata into the prompt

`avatar_rail.py:61-68` builds a `PromptSection` from
`perm_ctx.avatar_principal_name or perm_ctx.principal_user_id`, and `principal_user_id` is a raw
Slack user id set at `slack_connect.py:2727`. `_build_avatar_prompt` (`avatar_rail.py:170-207`)
interpolates it into the identity text. In avatar mode a Slack user id is therefore already in the
system prompt.

The project has accepted "a Slack id in the prompt" in one mode. It has never accepted a
permission flag there.

### 1.6 Answer

> *"Just an object the model can query anytime, or is it all dumped in context?"*

**Neither.** The dict travels intact from connector to adapter, parks in a ContextVar, and is read
only by host code: one tool's internal channel scoping (`slack_history.py`), one permission gate
(`owner_scopes.py`), one outbound file router (`send_file_to_user.py:295-304`), and the gateway's
reply addressing (`message_handler.py:483-484`).

The model's whole view of "where am I" is the word `slack`, plus a misleading `timestamp`.

---

## 2. The pipeline, hop by hop

| # | Hop | Location | Effect on metadata |
|---|---|---|---|
| 1 | Slack delivers | `slack_connect.py:874-875` — only `app_mention` and `message` subscribed | full envelope in memory |
| 2 | Filters | `:2508-2515`; `_USER_CONTENT_SUBTYPES = {"file_share"}` (`:81`) | non-content events dropped |
| 3 | Field extraction | `:2517-2534` | ~10 of ~25 fields read |
| 4 | Dedupe | `:2535-2539` | — |
| 5 | Text assembly | `:2552-2557`, the channel's prompt appended at `:2557` | becomes `content` |
| 6 | Attachments | `:2570-2592`, described into text at `:2589` | file objects reduced to prose |
| 7 | **`metadata` built** | **`:2605-2620`**, `slack_trigger` at `:2622` | 9–10 keys |
| 8 | Avatar enrichment | `:2674-2730` | +11 platform-neutral keys, group mode only |
| 9 | `Message(...)` | `:2640-2661`; `params = {"content": text, "query": text}` at `:2633` | attached at `:2656` |
| 10 | Envelope | `common/e2a/gateway_normalize.py:129-155` | `d["metadata"] = metadata` — **verbatim** |
| 11 | Websocket → agent server | `server/agent_ws_server.py:689-711` | only 4 internal keys stripped (`common/e2a/constants.py:103-110`); `app_id` added |
| 12 | Into `UserTurn` | `interface.py:1118-1126` | `chat_type`/`sender` only (`user_turn.py:147-160`) |
| 13 | Into ContextVars | `interface_deep.py:8825-8836` → `:5781-5842` | `request_id`/`project_dir` added |
| 14 | Host-side readers | `interface_deep.py:395-407`; `owner_scopes.py:61-88`; `slack_history.py:727,1032,1063`; `send_file_to_user.py:295-304` | — |
| 15 | Model | `runtime_prompt_rail.py`, `PromptAttachmentManager`, `user_turn.py` | **nothing from step 7** |

Second write site, for Block Kit clicks: `:2456-2470` — same shape minus `slack_event_id`, with
`slack_channel_type` guessed from the id prefix (`:2460-2462`) because `block_actions` carries none.

`slack_im_adapter.py:151-155` also builds a `{slack_channel_id, slack_channel_type}` dict, but that
is a synthetic argument for a gateway-side history refresh, not a request-metadata site.

---

## 3. Inventory: arrives / kept / forwarded / model-visible

The "arrives" column is the documented Slack Events API schema — the repo holds no inbound
fixture. **(inferred for that column only; all others are read from code.)**

### 3.1 Inbound `message` event

| Slack field | Arrives | Read by connector | In `metadata` | Model-visible |
|---|---|---|---|---|
| `ts` | yes | `:2518` | `slack_message_ts` `:2614` | **no — no reader anywhere** |
| `thread_ts` | yes | `:2559,2562` | `slack_thread_ts` `:2615` | no (reply addressing, `message_handler.py:483`) |
| `channel` | yes | `:2517` | `slack_channel_id` `:2609` | no (gates history tool) |
| `channel_type` | yes | `:2612` | `slack_channel_type` | no (validated `slack_history.py:728`) |
| `user` | yes | `:2510` | `slack_user_id` + `user_id` | no, except avatar mode (§1.5) |
| `team` | yes | `:2526` | `slack_team_id` `:2608` | **no — no reader anywhere** |
| `text` | yes | `:2552` | — | yes, as envelope `content` |
| `client_msg_id` | yes | `:2530` (fallback only) | — | no |
| `subtype` | yes | `:2513` (filter) | — | no |
| `bot_id` / `bot_profile` | yes | `:2508` (filter) | — | no |
| `files[]` | yes | `:2882` | — (prose at `:2589`) | filenames only |
| `parent_user_id` | yes | `:2135` (mention dedupe) | — | no |
| `blocks[]` | yes | **discarded** | — | no |
| `event_ts` | yes | **discarded** | — | no |
| `edited` | yes | **discarded** | — | no |
| `reactions[]` | not subscribed | — | — | via history tool only |

### 3.2 Outer envelope

| Field | Read | In `metadata` | Model-visible |
|---|---|---|---|
| `event_id` | `:2530` | `slack_event_id` `:2607` | no (snapshot binding, `slack_history.py:1032,1063`) |
| `team_id` | `:2524` | via `slack_team_id` | no |
| `authorizations[]` | `:2751-2762` (bot id discovery) | — | no |
| `event_time` | **discarded** | — | no |
| `api_app_id` | — | `app_id` injected at `agent_ws_server.py:697-701` | no |
| `token`, `event_context`, `context_team_id`, `is_ext_shared_channel` | **discarded** | — | no |

### 3.3 The forwarded dict

Nine keys always (`:2605-2620`), `slack_trigger` conditionally (`:2621-2622`), plus `request_id`
and `app_id` downstream.

**Four keys have no reader in either repo or in `tests/` beyond assertions:** `slack_message_ts`,
`slack_team_id`, `slack_user_id`, `slack_trigger`.

Avatar mode adds eleven more (`:2674-2730`), including `timestamp_ms` (`:2722`) — a **derived form
of the same message ts**. So in avatar mode the value the skill needed is forwarded twice and read
neither time.

---

## 4. Do other connectors do it differently?

Surveyed: telegram, discord, whatsapp, wechat, xiaoyi, dingtalk, feishu, wecom.

**No connector has a better pattern to copy. Most are worse.** The dominant shape is
write-only metadata: keys set on the inbound `Message` and read nowhere.

| Connector | Inbound site | Model-visible? |
|---|---|---|
| telegram | `telegram_connect.py:359` (dict `:368-374`) | no — `username`, `is_group_chat`, `message_id` have zero readers |
| discord | `discord_connect.py:191` (dict `:200-209`) | no — **7 of 8 keys have zero readers** |
| whatsapp | `whatsapp_connect.py:289` (dict `:298-303`) | no |
| wechat | `wechat_connect.py:1278` (dict `:1288-1294`) | no — but stuffs the **entire raw platform frame** into `raw_message`, zero readers |
| xiaoyi | `xiaoyi_connect.py:1341` (dict `:1327-1334`) | no |
| **dingtalk** | `dingtalk_connect.py:302`, dict `:752-756` | **yes — `sender_name`** |
| feishu | `feishu_connect.py:303`, assembled `:2709-2718` / `:1121-1173` | partial — `chat_type`; `principal_user_id` via avatar rail |
| wecom | `wecom_connect.py:827`, base `:909-919` | partial — same two paths as feishu |

DingTalk is the only connector that reaches the model with a *platform-supplied string*: it sets
`sender_name` from `chatbot_msg.sender_nick` (`dingtalk_connect.py:753`), and
`user_turn.py:157-159` renders it verbatim as the envelope's `sender` field.

**That is a precedent to avoid, not to follow.** A DingTalk display nickname is attacker-controlled
free text injected unescaped into the model's user turn. The same hazard exists on the
`interaction_context` prefix (`user_turn.py:162-169`), built from feishu/wecom display names at
`gateway/im_pipeline/interaction_context.py:172-188` and written at `im_inbound.py:569`.

Slack is, notably, the **only** connector whose platform-prefixed metadata is read by an
agent-side tool at all (`slack_history.py`). It is ahead of the others, not behind.

---

## 5. Does openjiuwen already have a slot for this?

**Yes — three, and none needs SDK work.** *(Verified directly: `deep_agent.py:1471-1495`,
`rail/base.py:141-146`.)*

1. **`inputs["run"]["context"]` → `RunContext.extra`.** `_normalize_inputs`
   (`openjiuwen/harness/deep_agent.py:1471-1495`) folds every key of `context` that is not a
   declared `RunContext` field (`openjiuwen/core/single_agent/rail/base.py:141-146`) into `extra`,
   and carries it through the single-round path (`react_agent.py:1971-1973`, landing on
   `ctx.extra["run_context"]`) and the task loop (`deep_agent.py:2387-2403` →
   `task_loop_controller.py:90-91` → `task_loop_event_executor.py:127-132`).

   **The host already uses this channel** — for cron (`interface.py:1193-1198`) and heartbeat
   (`gateway/heartbeat/heartbeat.py:189-195`). An ordinary Slack turn sets no `run`, so
   `run_context` is `None`.

   Caveat: `_to_effective_inputs` (`deep_agent.py:1566-1578`) rebuilds a fresh dict, so arbitrary
   top-level `inputs` keys are dropped. `run.context` is the only sanctioned passthrough.

2. **`Session` as ambient state.** `get_current_session()`
   (`openjiuwen/core/session/__init__.py:60-63`) is a ContextVar set by `with_session()` (`:66-77`),
   and `Session` is also passed as `session=` to every `Tool.invoke`
   (`ability_manager.py:1203`). `Session.update_state()/get_state()` is an arbitrary bag. The
   canonical worked example of *host data → ContextVar → tool* is
   `openjiuwen/harness/tools/worktree/rails.py:173-205`.

3. **`prompt_attachment_manager` is a public attribute on `DeepAgent`**
   (`openjiuwen/harness/deep_agent.py:261`), so the host can push a per-turn `<system-reminder>`
   section at will — which is exactly what `runtime_prompt_rail.py` already does.

**The one real limitation:** a plain `@tool` function receives only its declared arguments
(`openjiuwen/core/foundation/tool/function/function.py:65-85`; the schema extractor excludes only
`self`/`cls`, `callable_schema_extractor.py:209`). To read ambient data a tool must either call
`get_current_session()` itself or be a `Tool` subclass reading `kwargs["session"]`. `SlackHistoryToolkit`
sidesteps this entirely with a constructor-injected `metadata_provider` closure — which is why that
pattern is the one to extend.

Also worth knowing: `BaseMessage.metadata` exists on every message
(`openjiuwen/core/foundation/llm/schema/message.py:33`) but is **dropped before the provider call**
(`base_model_client.py:277-333`). It is an SDK-internal side channel, not a route to the model.

---

## 6. Recommendation

### 6.1 "Forward everything" is not sane. Curate.

Everything is *already* forwarded on the wire — the connector-to-adapter hop drops nothing
(`gateway_normalize.py:129-155`, `constants.py:103-110`). The question is only what becomes
**model-visible**, and there the costs diverge sharply by mechanism:

| Shape | Cost | Measured |
|---|---|---|
| Current 10-key metadata dict, JSON | ~424 chars, **~120 tokens** | serialised with representative Slack ids |
| Avatar-mode 21-key dict | ~776 chars, **~220 tokens** | ditto |
| Whole inbound `event` object | ~859 chars, **~245 tokens** | schema-reconstructed |
| Whole envelope incl. `authorizations`, `event_context` | ~1,537 chars, **~440 tokens** | ditto |
| **One** Slack file object (`file_share`) | ~1,532 chars, **~440 tokens** | ditto — and there can be several |

The multiplier matters more than the raw size, and it differs by surface:

- **Prompt attachment**: one copy, re-rendered every model call. Constant cost.
- **User-turn envelope**: one copy **per user turn**, accumulating in history. A 20-turn Slack
  thread pays 20×.

So a curated 4-field addition to the envelope (~35 tokens) costs ~700 tokens over a 20-turn
conversation. Dumping the full envelope (~440 tokens) costs ~8,800 over the same thread, and a
single file upload doubles that turn. **(inferred arithmetic from the measured sizes.)**

That settles it: an allowlist, not a dump. And the allowlist should be **identifiers and
timestamps only — never free text**, for the injection reason in §4.

### 6.2 The cheapest correct fix

`_sender_fields()` (`user_turn.py:147-160`) is *already* the metadata-to-model bridge, already
per-turn, already keyed off request metadata. Extend it:

```
slack_message_ts       from metadata["slack_message_ts"]
slack_message_iso_utc  derived — the ts_iso_utc lesson from slack_history.py:609-613
slack_thread_ts        from metadata["slack_thread_ts"]
slack_channel_id       from metadata["slack_channel_id"]
```

No connector change (all four are already forwarded), no wire change, no new tool, no SDK work.
It also lets the misleading envelope `timestamp` (`:115`) be disambiguated — ideally by renaming it
to `received_at` and stating its timezone honestly rather than hardcoding `Asia/Shanghai`.

### 6.3 If a tool is wanted instead

Model it on `SlackHistoryToolkit`, not on anything new.

- **Name**: `get_current_message_context` (matches `get_current_slack_channel_history`).
- **Arguments**: **none.** This is the whole security argument — there is no parameter for a model
  to point at another channel. Strictly stronger than the history tool, which at least takes
  `hours`/`all_history`.
- **Returns**: `{ok, channel: "slack", channel_id, channel_type, message_ts, message_iso_utc,
  thread_ts, permalink, user_id, team_id, trigger}`.
- **Wiring**: a `metadata_provider` closure over `self._runtime_cron_tool_context`, exactly as
  `interface_deep.py:6163-6166,6188-6192`.
- **Gate**: its own filter, mirroring `_filter_slack_history_request_metadata` (`:395-407`) —
  fail closed on a non-`slack` channel and on empty `slack_channel_id`. Do **not** reuse
  `slack_history_digest_allowed`: that flag authorises *reading a channel's history*, a far larger
  capability than *naming the message you were just sent*. Conflating them would either
  over-restrict this tool (it is useful in every channel) or silently widen that one.

### 6.4 Security boundary

**Never model-visible:**

- **`slack_history_digest_allowed`** — this is the gate's own output. Three reasons, in order of
  severity: (i) a tool that trusted a model-relayed copy would be trivially bypassable; (ii) it
  tells the model which channels are privileged, which is reconnaissance; (iii) a model that can
  read a permission decision is one step from a model that argues about it. The existing filter is
  right to consume it and discard it (`interface_deep.py:395-407`), and any new surface must
  strip it explicitly rather than rely on it not being asked for.
- **`authorizations[]`, `token`, `event_context`** — currently discarded at the connector, and must
  stay discarded. `token` is the Slack verification token, i.e. a secret.
- **Any free-text platform-supplied string** — display names, nicknames, channel names. See the
  DingTalk `sender_name` path in §4. Ids are opaque and injection-inert; names are not.

**Acceptable, with the boundary already drawn elsewhere:**

- `slack_message_ts`, `slack_thread_ts` — public identifiers within a conversation the model is
  already participating in. Benign.
- `slack_channel_id`, `slack_channel_type` — the model can already post to this channel; knowing
  its id grants nothing new.
- `slack_user_id` — already returned to the model by the history tool
  (`slack_history.py:626-627`) and already in the system prompt in avatar mode (§1.5). Consistent
  to include, but note the model may echo it into a public reply.
- `slack_team_id` — harmless and near-useless; omit for tidiness.

One caveat on `permalink`: `slack_history.py` builds permalinks (`:489`, used at `:607`) for history records, so
the pattern exists — but a permalink embeds the channel id and workspace, so it inherits whatever
boundary `slack_channel_id` gets, not a looser one.

### 6.5 Sequencing

**Cheap now (hours, low risk):**

1. Extend `_sender_fields()` (`user_turn.py:147-160`) with the four fields in §6.2. Fixes the
   reported bug outright. No connector, wire, or SDK change.
2. Fix or rename the envelope `timestamp` (`:111,115`) and the hardcoded `Asia/Shanghai`
   (`:114`) — a correctness bug affecting every channel, not just Slack.
3. Keep `slack_event_ts` and `edited` out; they add nothing the ts does not already give.

**Medium (a day, needs a test for the fail-closed path):**

4. `get_current_message_context` per §6.3, with its own gate. Worth doing only if skills need
   metadata beyond the four fields — otherwise item 1 subsumes it.

**Real refactor (do not bundle):**

5. A normalised per-connector "channel context" contract. §4 shows eight connectors each inventing
   their own key names, most of them write-only, one of them shipping the entire raw platform frame
   (`wechat_connect.py:1293`). Unifying these behind one allowlisted, injection-safe struct is a
   genuine cross-cutting change touching every connector and `user_turn.py`.
6. Routing that struct through `inputs["run"]["context"]` → `RunContext.extra` (§5) so rails and
   tools share one source of truth instead of the current split between `_CRON_TOOL_METADATA`,
   `TOOL_PERMISSION_CONTEXT` and `UserTurn.metadata`.

Items 5 and 6 are the "should we refactor so all metadata is available" answer: **yes eventually,
but the answer to the immediate problem is item 1, and item 1 does not depend on them.**
