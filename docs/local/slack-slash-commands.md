# Slack slash commands: can jiuwenswarm use them?

Status: investigation only. No implementation, no source changes, no Slack app
configuration changes, no API calls. Nothing below was tested against a live
workspace.

## 0. Which tree the line numbers refer to

Every `file:N` anchor is a line as it stands on `local/deployed` = `1a74ee462`,
which this document is committed against. Anchors into
`slack_bolt` / `slack_sdk` refer to the running venv
`/home/jiuwenswarm/venvs/current/lib/python3.12/site-packages/`
(`slack_bolt.__version__ == "1.30.0"`, `slack_bolt/version.py:3`).

Claims about **Slack platform behaviour** — as opposed to what this repo's code
does — are marked `[platform]` and are stated from knowledge of the Slack API,
not from anything read in this repo. Where a platform claim was checkable
against the installed SDK, that check is cited. Anything genuinely uncertain is
marked `[inferred]`.

---

## 1. Verdicts

### Q1. Could jiuwenswarm map its own commands to Slack slash commands?

**Possible, with caveats — and it is more necessary than it looks.**

The commands already exist as a first-class product concept
(`GatewaySlashCommand`, `slash_command.py:22-36`; `FIRST_BATCH_REGISTRY`,
`slash_command.py:349-447`; the user-facing table in `docs/zh/Slash命令表.md`).
Bolt's `app.command()` is available in the installed version
(`slack_bolt/app/async_app.py:997`) and needs **no** transport change: the
Socket Mode adapter converts any envelope payload into a `BoltRequest` and lets
the app route it (`slack_bolt/adapter/socket_mode/async_internals.py:18`), which
is the same property the connector already relies on for button clicks
(`slack_connect.py:876-879`).

The caveats are that each command name must be declared **by hand in the Slack
app configuration** (§4), and that the connector must synthesise a session and a
posting anchor that a slash-command payload does not carry (§5.3).

The under-appreciated part: today `/review 123` typed into Slack **does not
work at all**. `[platform]` Slack intercepts any message whose text begins with
`/`; if the name is not a registered command it shows the sender an ephemeral
"`/review` is not a valid command" and the message is never posted, so no
`message` event is emitted and the connector never sees it. Independently, the
gateway would not have interpreted it anyway for the general control commands
(§3.2). So this is not "a nicer way to type an existing command" — for Slack it
is the *only* way any of these commands can be typed.

### Q2. Could a *skill* introduce a slash command?

**Not realistically.** Two independent blockers, either of which is fatal on
its own:

1. `[platform]` Slack slash commands are declared in app configuration, not at
   runtime. There is no Web API method to create one. Changing the set requires
   an operator editing the app (or its manifest) and reinstalling to the
   workspace — the same reinstall the setup docs already call out for scope
   changes (`docs/en/InternationalChannels.md:337`). A skill installed at 14:02
   cannot cause `/pr-report` to exist at 14:03.
2. Skills declare no invocable name today. `_parse_skill_md`
   (`skill_manager.py:2689-2750`) reads `name`, `description`, `version`,
   `author`, `tags`, `allowed_tools` and nothing command-shaped; `name` even
   falls back to the filename (`:2737-2739`). The openjiuwen registry is
   thinner still — `Skill` is `name` / `description` / `directory`
   (`agent-core/openjiuwen/core/single_agent/skills/skill_manager.py:11-29`),
   with `name` taken from the directory name (`:117`).

The workable version of this ask is a **subcommand**, not a slash command:
`/jiuwenswarm pr-report` where `pr-report` is looked up against the live skill
registry at call time. That needs no manifest change per skill and is covered by
§4.2. Calling that "a skill-defined slash command" would be a stretch, but it
delivers the operator's actual goal.

### Q3. Is the mechanism inherently restricted to specific use cases?

**Partly, and the restrictions bite in exactly the places this use case cares
about.** `[platform]` The three that matter: the command set is static and
operator-managed; the handler has 3 seconds to acknowledge; and the payload
carries a single flat text argument with a hard length ceiling — nothing like a
50-line prompt. None of these rules out the report use case, but together they
force the design into a specific shape (§7).

---

## 2. Recommendation up front

**Ship one dispatcher command. Do not attempt per-skill commands.**

Register a single `/jiuwenswarm` (plus, optionally, one alias) in the app
configuration once, and route its first word to a subcommand table that reuses
the existing parse and prompt machinery. This is the recommendation because:

- One manifest entry, once. Adding a subcommand later is a code change and a
  release, not an operator touching the Slack app and reinstalling.
- It composes with the registry that already exists rather than inventing a
  second command vocabulary.
- It sidesteps the name-collision problem entirely `[platform]`: slash command
  names are workspace-global across all installed apps, so claiming `/review`
  fails if any other app in the workspace already owns it, and `/status`,
  `/remind`, `/invite`, `/topic`, `/dm`, `/away`, `/shrug` and friends are
  Slack built-ins that cannot be claimed at all. `/skills`, `/mode`, `/branch`
  and `/new_session` are all plausible collisions in a shared workspace.

Rough size: **1.5–3 days** for the dispatcher with two subcommands
(§8). Per-skill commands: **do not build**.

---

## 3. What exists today

### 3.1 The Slack connector handles no commands

`slack_connect.py:873-882` is the complete handler registration:

```python
app = AsyncApp(token=self.config.bot_token.strip())
app.event("app_mention")(self._handle_app_mention)
app.event("message")(self._handle_message_event)
app.action(_QUESTION_ACTION_ID_RE)(self._handle_question_action)

handler = AsyncSocketModeHandler(app, self.config.app_token.strip())
```

No `app.command`, no `app.view`, no shortcut. The one `app.action` is for
buttons on messages the bot posted itself (`_QUESTION_ACTION_ID_RE` at `:204`,
handler at `:2186`).

The comment at `:876-879` is the load-bearing precedent for how little transport
work a command would need:

> Interaction payloads arrive on the same Socket Mode connection as the events
> above and need no subscription and no Request URL of their own: the handler
> forwards every envelope it receives to the app, which routes a `block_actions`
> payload by the `action_id` its buttons were given.

That is confirmed in the installed SDK: `async_internals.py:18` builds an
`AsyncBoltRequest` from `req.payload` for **every** envelope type, and
`SocketModeRequest` (`slack_sdk/socket_mode/request.py:7-47`) is type-agnostic.
So a `slash_commands` envelope would reach `app.command(...)` with **zero**
change to `start()` beyond the one registration line. `[inferred, but strongly
supported]` — the SDK path is verified; that Slack actually delivers slash
commands over the socket rather than requiring a Request URL when Socket Mode is
on is `[platform]` knowledge, not something visible here.

### 3.2 A first-class command vocabulary exists — and Slack is excluded from it

`GatewaySlashCommand` (`slash_command.py:22-36`) defines the gateway-side set:
`/new_session`, `/mode`, `/switch`, `/skills`, `/skills list`, `/branch`,
`/rewind`, `/review`, `/security-review`, `/join`, `/exit`.
`parse_channel_control_text` (`:154`) is the single parser;
`FIRST_BATCH_REGISTRY` (`:349-447`) is a metadata table of `id`,
`canonical_text`, `scope` (`gateway` | `client`), `req_method` and notes. The
user-facing catalogue is `docs/zh/Slash命令表.md` and the architecture rules are
`docs/en/SlashCommandArchitecture.md`.

So the answer to "does a first-class command concept exist to be mapped" is
**yes, and it is already a documented SSOT with a registry**. This is the single
most useful finding: a Slack mapping does not have to invent a command model.

But two gates currently exclude Slack:

- `message_handler.py:244-251` sets `_control_channel_types` to feishu, xiaoyi,
  dingtalk, whatsapp, wecom, wechat. Slack, Telegram and Discord are **absent**.
  `:1526-1528` returns `False` for any channel not in that set, so `/mode`,
  `/new_session`, `/switch`, `/skills list`, `/branch`, `/rewind`, `/join`,
  `/exit` are never interpreted on Slack.
- `/review` and `/security-review` are the exception: `message_handler.py:3823`
  parses them for **all channels** ("Resolve /review and /security-review slash
  commands (all channels)"), injecting a built prompt at `:3837-3845`.

So on paper `/review 123` should work on Slack. `[platform]` In practice it
cannot, because Slack swallows the text before it becomes a message event
(§1/Q1). This looks like a latent dead path rather than a working feature —
worth flagging separately from this investigation.

### 3.3 Scopes

No manifest, no app-config file and no scope list exists in the repo. The app is
set up by hand through the Slack UI per `docs/en/InternationalChannels.md:318-340`,
which documents the intended bot token scopes: `chat:write`,
`app_mentions:read`, `im:history`, optionally `channels:history`, `users:read`,
`groups:history`, plus the app-level token scope `connections:write`.
`commands` is **not** in that list.

**The scopes actually granted to the deployed app cannot be determined from this
repo.** Doing so requires `auth.test` / `apps.permissions` against the live
token, which is out of scope here. What can be said: the documented setup does
not include `commands`, so the working assumption is that it is not granted.
`[platform]` `commands` is added implicitly when a slash command is created in
app configuration, and the app must then be reinstalled — the same reinstall
`:337` already warns about.

### 3.4 Skills declare nothing invocable by name

- `_parse_skill_md` (`skill_manager.py:2689-2750`): frontmatter is parsed with
  `yaml.safe_load` into an open `meta` dict, then normalised for `name`,
  `description`, `version`, `author`, `tags`, `allowed_tools`
  (`:2737-2746`). Unknown keys are **preserved** in `meta` — so a `command:`
  key would survive parsing — but nothing reads one. There is no alias, trigger
  or entry-point concept.
- openjiuwen is thinner: `Skill(name, description, directory)`
  (`agent-core/.../skills/skill_manager.py:11-29`), description from frontmatter
  (`:84-101`), name from the directory (`:117`).
- `skills_state.json` (`skill_manager.py:434`, schema at `:4082-4104`,
  helpers in `skilldev/state_utils.py:22-55`) records `marketplaces`,
  `installed_plugins`, `local_skills` and per-skill `{"enabled": bool}`. It is
  an install ledger, not a command table.
- The one by-name invocation that exists is `/skills use <name> <query>`
  (`interface.py:771-786`) — a text prefix parsed out of the user's turn,
  extracting exactly one skill name and passing the remainder through as the
  query.
- Skills **are** hot-swappable without a restart:
  `_refresh_skill_rails_after_change` (`interface.py:984-994`) re-scans
  `skills_dir` via `reload_skills()` rather than rebuilding the agent. This is
  precisely why a *subcommand* resolved at call time works and a *manifest
  entry* does not.

---

## 4. The manifest-registration constraint

### 4.1 There is no runtime registration path

`[platform]` Slash commands are part of an app's configuration. They can be
created through the app settings UI or by updating the app manifest
(`apps.manifest.update` exists for that, and requires a **configuration token**
— a separate, rotating credential class, not the bot or app token this connector
holds, `slack_connect.py:746-747`). Even taking that route, the change is to the
app definition and the app must be reinstalled to the workspace. There is no
"register this command for the next hour" API.

Docs: <https://docs.slack.dev/interactivity/implementing-slash-commands/>,
<https://docs.slack.dev/app-manifests/>.

Consequences:

- **A skill cannot add a command at install time.** Not with a workaround, not
  with a clever token. This is a platform fact, not a gap in this codebase.
- **A manifest generation step is a bad trade.** It would mean: skill installed
  → regenerate manifest → operator applies it via a configuration token →
  reinstall the app to the workspace → every user's client picks up the new
  command. That is an operator-in-the-loop, re-authorisation-triggering step
  bolted onto what is supposed to be a runtime action, and it introduces a
  credential class the product does not otherwise hold. Not worth it.

### 4.2 The dispatcher is the realistic shape

One registered command, subcommands resolved in code:

```
/jiuwenswarm pr-report jiuwenswarm
/jiuwenswarm review 123
/jiuwenswarm skills
```

`[platform]` The whole text after the command name arrives as a single
`text` field, so subcommand parsing is entirely ours. One manifest entry covers
every present and future subcommand, including ones backed by skills that did
not exist when the app was installed.

The cost is discoverability: Slack's autocomplete will only ever offer
`/jiuwenswarm` plus whatever static hint string the app config carries, so
`/jiuwenswarm help` has to do the work the platform would otherwise do.

---

## 5. The 3-second rule

`[platform]` A slash command handler must respond within 3 seconds or the caller
sees an operation-timeout error. The acknowledgement can be empty; the real
answer can follow, either by posting normally or via the payload's
`response_url`, which `[platform]` accepts up to 5 delayed responses within 30
minutes.

### 5.1 The connector already has the right shape

`_handle_question_action` (`slack_connect.py:2186`) is exactly this pattern, and
its docstring states the reasoning (`:2190-2194`):

> Acknowledged first and unconditionally. Slack gives an interaction three
> seconds before it shows the person who clicked an error, and everything below
> — two API calls and a dispatch into the gateway — can take longer than that.
> The acknowledgement says the click arrived, not that the answer was accepted.

`await ack()` is at `:2210`, before every check and every await that follows.
The same shape transfers to a command handler unchanged: `ack()` first, then the
work.

There is a second, weaker precedent in the message path:
`_acknowledge_request` (`:2585`, defined at `:2834`) posts a reaction or a text
acknowledgement before attachments are downloaded, with a comment (`:2575-2582`)
about not leaving the poster without a sign the message was seen. Same
instinct, different mechanism.

**Verdict: the 3-second rule is not a feasibility problem.** It is already
solved in this connector for a payload type with the identical constraint. The
report taking two minutes is irrelevant once `ack()` is unconditional and first.

### 5.2 What is *not* already solved

The button handler answers a question that is already anchored to a posted
message — it knows the channel, the message and the thread, because the bot
posted them. A slash command payload carries `channel_id`, `user_id`, `team_id`,
`command`, `text`, `trigger_id` and `response_url` — but **no `ts`**. The
connector's session key is derived from a message timestamp
(`slack_connect.py:2567-2569`):

```python
session_id = f"slack_{team_id or 'default'}_{channel_id}_{user_id}"          # DM
session_id = f"slack_{team_id or 'default'}_{channel_id}_{root_thread_ts}"   # channel
```

and the dispatched `Message` carries `slack_message_ts` / `slack_thread_ts` in
its metadata (`:2605-2620`, `Message` built at `:2638`). A command has neither.

The clean fix is to post a placeholder first — `ack()`, then
`chat.postMessage("Running `/jiuwenswarm pr-report`…")`, then use *that*
message's `ts` as both the thread anchor and the session key, then dispatch the
same `Message` shape the text path builds. That reuses the entire existing
reply, streaming and approval-button path with no changes to it, and it gives
the caller immediate visible feedback. It is a real chunk of the work, but it is
plumbing, not a design risk.

---

## 6. Where the prompt comes from

The operator is right that this is the hard part, but the codebase has already
answered it once.

### 6.1 The existing answer: a stored prompt keyed by command name

`/review 123` does not send "123" to the agent. `message_handler.py:3837-3845`
replaces the whole turn:

```python
review_prompt = build_review_prompt(pr_arg)
msg.params["query"] = review_prompt
```

`build_review_prompt` (`prompts/review_prompt.py:10-39`) is a 30-line template
with the short argument interpolated at the end (`PR number: {args}`) and the
configured output language appended. `build_security_review_prompt`
(`prompts/security_review_prompt.py`, 263 lines) is the same idea at four times
the size.

**This is exactly the operator's use case, already built.** `/pr-report` is
`build_review_prompt` with different words in the file. The 50-line prompt lives
in `prompts/`, the command carries the one argument that varies, and the mapping
is a line in a table. No new mechanism is required.

`[platform]` The argument ceiling is not a problem for this shape: the `text`
field is a single line of whatever the user typed, and a report's varying part
is a repo name or a PR number, not prose.

### 6.2 The skill-supplies-its-own-instructions option

For a skill-backed subcommand, the prompt could instead come from the skill's
own `SKILL.md` body — `_parse_skill_md` already returns it as `meta["body"]`
(`skill_manager.py:2748`), and `/skills use <name> <query>`
(`interface.py:771-786`) is the existing way to point a turn at a named skill.
So `/jiuwenswarm pr-report` could desugar to `/skills use pr-report <text>` and
let the rail do the rest.

This is attractive because it needs no per-command Python. It is weaker because
a `SKILL.md` body is written as reference material for an agent that has already
decided to use the skill, not as a self-contained task instruction — quality
would be a per-skill lottery. Worth prototyping; not worth committing to
sight-unseen.

### 6.3 Third option: a config-supplied prompt

Rejected. It puts a 50-line prompt in `config.yaml`, which is a template file
where every key must be enumerated, and makes the report's definition an
operator concern rather than a product one. §6.1 is strictly better.

### 6.4 How this composes with a channel's standing prompt

`scopes` gives a channel a `mode` and a standing `delivery.prompt`. That prompt
is appended to **every** message the bot answers in the channel a rule names,
appended rather than prepended, and whichever trigger woke it.

**These compose; they do not duplicate.** They answer different questions:

| | `delivery.prompt` | a command's prompt |
| --- | --- | --- |
| answers | "what is always true in this channel" | "what task is being asked for" |
| set by | the operator, in config | the product, in `prompts/` |
| scope | ambient, every message | one invocation |
| example | "This is a support channel. Be terse." | the 30-line PR-review template |

A slash-command turn would sensibly get both: the command's template as the
query, the channel's standing prompt appended exactly as it is for a typed
message. There is one thing to decide rather than inherit — whether a command
invocation should get the standing prompt at all — and the answer is probably
yes, for the same reason a standing prompt applies whichever trigger woke the
bot: a channel-wide instruction like "reply in English" should not silently stop
applying because the user reached the agent by a different door.

The overlap risk is not technical but conceptual: an operator who discovers
`delivery.prompt` first will be tempted to encode a report template
there and use `mode: all` as the trigger. If commands land, the documentation
should be explicit that the standing prompt is ambient context and not a task
template.

---

## 7. Response visibility

`[platform]` A slash command response is ephemeral by default (`response_type:
"ephemeral"` — only the caller sees it, and it is not persisted); setting
`response_type: "in_channel"` posts it visibly, along with an echo of the
invocation.

Both are defensible for a report and they mean different things:

- **Ephemeral** — the report is for the person who asked. Nothing else in the
  channel changes. Good for `/jiuwenswarm help` and for anything that might be
  noisy or wrong.
- **In-channel** — the report is a channel artifact others will read, react to
  and thread on. This is almost certainly what a PR report wants.

There is a third consideration specific to this connector: the streaming reply
path and the approval-button path both operate on a **real posted message** —
buttons require `enable_streaming` and post into the channel
(`docs/en/InternationalChannels.md:438`). An ephemeral response cannot carry
working buttons for an approval, and cannot be edited by the streaming updater.
So if a command-triggered turn can ask for approval or stream, the placeholder
described in §5.2 must be a real in-channel message and ephemeral is only
available for immediate, terminal answers like errors and help.

Recommendation: ephemeral for rejections, errors and help; in-channel for
anything that starts real work. Do not make it configurable in v1.

---

## 8. Security

`[platform]` A slash command is invocable by anyone who can type in the channel,
including a channel the bot has not been invited to — the command belongs to the
workspace, not to the bot's membership. That is a genuinely wider door than
anything the connector faces today.

The existing gates and whether they carry over:

- **`allow_from`** (`slack_connect.py:749`, `is_allowed` in
  `channel_manager/base.py:170`). Applies cleanly — the payload carries
  `user_id`. The button handler is the precedent, and its comment
  (`slack_connect.py:2222-2232`) is the argument for applying it here too:
  > An approval is exactly the kind of thing the allow list exists to gate:
  > anyone who can see the message can press the button, and membership of the
  > channel is not permission to drive the agent.

  A command that triggers real work is the same category. It must check
  `is_allowed(user_id)` before doing anything, and — unlike the button path,
  which returns silently at `:2232` — it should answer ephemerally, because a
  slash command that appears to do nothing reads as a bug.
- **`allowed_channel_ids`** (`:750`, enforced at `:2545-2547`). Applies, and the
  payload carries `channel_id`. Note the existing check is skipped for DMs and
  for any conversation a scope names; a command handler should apply it for any
  non-DM invocation with no exception.
- **The dedupe layer** (`slack_dedup.py`, `_remember_event` at `:2540`, defined at `:3228`) keys on
  event ids and message timestamps. A command payload has neither. `[platform]`
  Slack does not retry slash commands the way it retries events, so this is
  probably a non-issue — but a double-click sending two identical commands two
  seconds apart is a user-level reality that nothing would currently catch, and
  a report is expensive enough to want a short per-`(user, command)` cooldown.

One thing that does *not* carry over and needs a decision: everything today is
either a DM or a message in a channel the bot was invited to. A slash command
can arrive from a channel the bot is not a member of, in which case
`[platform]` posting the answer requires the bot to join or will fail outright.
`allowed_channel_ids` covers this if it is set, and does not if it is empty —
which is the default (`:750`). A command handler should probably refuse
non-member channels explicitly rather than fail at post time.

---

## 9. Size estimate

Assuming the dispatcher shape from §4.2 and §5.2:

| piece | size |
| --- | --- |
| `app.command("/jiuwenswarm")` registration + handler skeleton with `ack()` first | small — one line at `:880` plus a handler modelled on `_handle_question_action` |
| subcommand table + parse + `help` | small, and mostly a mapping onto `FIRST_BATCH_REGISTRY` |
| placeholder-post → session key → `Message` dispatch (§5.2) | **the bulk of it**; touches session identity, so it needs care |
| `allow_from` / `allowed_channel_ids` / cooldown gates | small, all precedented |
| one report prompt in `prompts/` | small — `review_prompt.py` is 39 lines including licence header |
| config: enable flag, command name | small; note the template must list every key |
| tests | moderate — no test double for a command payload exists yet |
| docs: `InternationalChannels.md` setup steps, `Slash命令表.md` entry | small |
| operator one-time: create the command in app config, reinstall | minutes, but it is a human step and a re-authorisation |

**1.5–3 days** for a working `/jiuwenswarm help` + one report subcommand,
including tests and docs. Each additional subcommand afterwards is hours.

Per-skill slash commands: **not estimated, because they should not be built.**
The subcommand form (`/jiuwenswarm <skill-name>`, resolved against the live
registry) is a few hours on top of the dispatcher and delivers the same
outcome.

---

## 10. Is this a bad idea?

**No — but the framing should change.**

The weak version of this idea is "slash commands are a nicer way to type things
you can already type". That version is not worth much on its own.

The strong version is what §3.2 turned up: the product's documented command
vocabulary is **unreachable from Slack**. The gateway excludes Slack from
`_control_channel_types`, and even the two all-channel commands are unreachable
because `[platform]` Slack eats unregistered slash text before it becomes an
event. Registering a command is the only mechanism by which a Slack user can
issue a jiuwenswarm command at all. That makes this a gap-closer rather than a
nicety.

Three honest caveats:

1. **The prompt problem is already solved and is not the hard part.**
   `build_review_prompt` is the pattern; the operator's instinct that it would
   be hard is understandable but, in this codebase, wrong.
2. **Per-skill commands are a dead end** and should be closed off explicitly in
   whatever design follows, so nobody spends a week rediscovering that
   `apps.manifest.update` needs a configuration token and a reinstall.
3. **Session identity is the real work.** Everything else has a precedent in
   this file; §5.2 does not.

If only one sentence survives: **a single dispatcher command is feasible and
worth doing, and per-skill slash commands are not possible without an operator
reinstalling the Slack app every time a skill is installed — so build the
dispatcher and resolve skills as subcommands at call time.**
