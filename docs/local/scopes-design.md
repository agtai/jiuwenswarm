# `scopes` — one addressing scheme for per-conversation and per-user rules

Status: **partly implemented.** Steps 1, 2 and 3 of §11 are in the tree, and so is
the first half of Step 5 — D15's stop button and the turn-initiator record it
reads. Step 4 (`people:` / `roles:`) is not built yet — it is being implemented on
another branch as this is written. Step 5's second half, the `clicks` section
itself and F2, is also not built. What shipped is narrower than what is written
here, and the gap is deliberate rather than accidental:

- **Axes**: `channel`, `chat` and `user`, with `not` on identity. `role` alone is
  left in `DEFERRED_AXES` in `jiuwenswarm/common/scopes/schema.py` — naming it, or
  naming it inside a `not:`, **drops the whole scope** with a warning, because an
  unresolved role names nobody and `not: {role: admin}` would then match everyone.
  `not:` on a non-identity axis is refused for §4.4's reason and drops the scope too.
- **Layers**: the identity axis counts **once** towards `specificity`, however it is
  spelled, so `{channel, chat, user}` is layer 3 and adding a `not:` to it does not
  make it layer 4. Two scopes at one layer can be incomparable — `{channel, user}`
  against `{channel, chat}` — and those tie, settled by position in the file.
- **The sender** reaches the matcher from the connector, not from `AgentRequest`.
  Slack reads `event["user"]` per message; a turn resumed by a click resolves
  against the turn's initiator rather than the clicker, per D13.
- **Sections**: `delivery`, `agent` and now `permissions`. `agent` holds exactly one
  key, `model_name`, and it is the one that was already working: the connector
  settles it and puts it on the request as `params["model_name"]`. `permissions` is
  folded through agent-core's `narrow_permissions` (`jiuwenswarm/common/scopes/permissions.py`)
  and read by the runtime hook (`scope_permissions.py`) on `channel` and `chat`
  alone, at every tool call — the `user` axis still waits on §8.4, so a `permissions`
  scope naming a person does not yet narrow anything.
- **Connectors**: Slack alone resolves `delivery` and `agent` — nothing else calls
  that resolver, so `web`'s declared `delivery` section is registered but inert.
  `permissions` is different: `TOOL_PERMISSION_CHANNEL_ID` / `_CHAT_ID` are set at
  every runtime entry point regardless of connector, so a `permissions` scope
  naming `web`, `__cron__` or `__heartbeat__` already applies — the last two
  declare `permissions` alone.
- `people:` and `roles:` (§8.2, §8.3) do not exist in code at all.
- **Clicks**: `clicks` is a section, in `ENTRY_KEYS` and in `SUPPORTED_SECTIONS`,
  declared by Slack for both of its gestures and enforced at both of them. F1, F2
  and D15's floor are all code. What remains design is the third of §8.5's three
  categories — a cron turn no gesture can name — which is an addressing problem
  rather than an authorization one and is sequenced after this step.

With the shipped `scopes: []` the whole path short-circuits and the connector
follows `channels.slack` alone.

Read the sections below as the design they always were. Where they describe
behaviour, check it against the code before relying on it.

Everything here lives in **jiuwenswarm**. agent-core provides the hook the permission
half needs — `ToolPermissionHost.permission_scene_hook`, described in
`openjiuwen/harness/security/host.py` as *"host scene: intervene before the general
tiered decision (e.g. digital avatar / owner_scopes)"*.

**That hook is one slot, not an extension point.** It is a single optional field on a
dataclass with exactly one call site (`harness/rails/security/tool_security_rail.py`),
no registry and no chain, and jiuwenswarm's one implementation is a closure in
`interrupt_helpers.py` already carrying four concerns: the skills-rebuild bypass, the
`ask_user` bypass, the digital avatar, and generic `owner_scopes`. `scopes` is therefore
a **fifth branch inside that closure**, not a parallel implementation beside it — which
makes the ordering within the closure part of this design rather than an implementation
detail (§8.3). Two mitigations: jiuwenswarm builds `ToolPermissionHost` at two sites and
the team path (`agents/swarm/providers/member_rails.py`) leaves its scene slot free; and
agent-core exposes `tool_permission_checks_active` on the same host — a purpose-built
per-entry-point gate — if a cheaper hook is wanted for the coarse cases.

| # | decision | recorded in |
| --- | --- | --- |
| D1 | `scopes` is **top-level**, not nested under `channels` | §2.3 |
| D2 | composition is decided by the value's **type**, not its key name | §5 |
| D3 | `permissions` narrows order-independently; `agent` and `delivery` cascade in order | §5.4 |
| D4 | **v1 tightens only**; negative matching removes the need for `override:` | §4.3 |
| D5 | `user` and `role` are one axis and **OR**; `not` is set difference | §4.2 |
| D6 | `not` applies to the **identity axis only** in v1 | §4.4 |
| D7 | opt-in **is** the capability declaration; there is no separate boolean | §7 |
| D8 | roles are **named sets of people** and never carry permissions | §8.3 |
| D9 | identity is an **opaque per-channel bag**; `delivery` reuses `RoutingKey` | §8.1 |
| D10 | `allow_from` / `allowed_channel_ids` are upstream and **stay** as layer 0 | §2.2 |
| D11 | unattended channels degrade `ask` to `deny` rather than hanging | §7.3 |
| D12 | a restricted principal must not be able to enqueue unrestricted work | §9.2 |
| D13 | a **click** is authorized like a sender, not like a turn; scopes name who may click | §8.5 |
| D14 | a key's section is decided by who **acts** on it, not by who resolves it | §3 |
| D15 | whoever started a turn may **stop** it; `clicks.stop` narrows who *else* may | §8.5 |
| D16 | a message arriving **mid-turn** is governed by `delivery.mid_turn`; the connector decides | §3.3 |
| D17 | the runtime-facing section stays **`agent`**: it is the per-conversation slice of an agent *definition* | §3.4 |

---

## 1. Motivation

Today any user in any channel the bot is in can ask it anything, and the bot will
do anything it is capable of. Two axes of restriction are wanted and neither
exists:

- **per conversation** — this channel is read-only; that one runs a different model
- **per sender** — an admin may do anything; a collaborator may only read

The Slack connector reached that first, per conversation and for itself alone:
a mode, a standing prompt and a model, settled per channel by the connector. Every
other connector that wants the same thing must reinvent it, and none of them can
express the sender axis at all.

The observation that makes a general mechanism cheap: **all three axes now reach the
runtime.** In `jiuwenswarm/common/e2a/agent_compat.py` on upstream `develop`:

```python
return AgentRequest(
    request_id=env.request_id or "",
    channel_id=env.channel or "web",   # platform:     "slack", "web", "__cron__"
    session_id=env.session_id,
    chat_id=env.chat_id,               # conversation: the Slack channel, Feishu chat, …
    user_id=env.user_id,               # sender — added by 403fe354a, 2026-08-24
)
```

`chat_id` is set by Slack, Feishu, Telegram, DingTalk and WeCom alike and always
survived the wire. The sender used to be dropped here; `403fe354a`
(*refactor(agentos): Gateway 去业务状态化，适配多用户场景*) now carries it. An earlier
draft of this document listed that one line as a prerequisite to be written — it has
since been written by someone else, for unrelated reasons. §8.4 records what the fix
does and does not give us.

So a generic mechanism needs no new plumbing at all. It needs a matcher over fields
that are already there.

## 2. What it does not replace

### 2.2 Retained (D10)

| key | origin |
| --- | --- |
| `allow_from` | upstream, since the initial commit; on `BaseChannel.is_allowed` |
| `allowed_channel_ids` | upstream, mirror of #1307 |

These are upstream keys in other people's deployments. They are not ours to remove,
and they sit naturally at layer 0 because they answer a *prior* question:

```
allowed_channel_ids   does the bot respond in this conversation at all?
allow_from            may this person drive the bot at all?
        ↓ only if both pass
scopes                and then, with what delivery / model / permissions?
```

Coarse gate first, fine rules after. A scope never re-opens what layer 0 refused.

**The clean reading above is upstream's intent, not uniformly its behaviour.**
`allow_from` is passed the *conversation* id rather than the sender on two connectors
(`dingtalk_connect.py`, `wecom_connect.py`), and `BaseChannel.is_allowed` splits its
entries on `|`, which is a composite identity already being smuggled through a string.
It is also empty by default and therefore fails open. This is an argument *for*
`scopes` — the two questions above are genuinely distinct and layer 0 currently
conflates them on some platforms — but the conflation must not be repeated here:
a scope's `user` axis always means the sender, on every platform, or it means nothing.

### 2.3 Why top-level (D1)

Nesting under `channels.<platform>` reads more naturally and was the first
instinct. It fails on three counts:

- **Cross-platform identity.** `{user: X}` meaning "this person, anywhere" is a
  real requirement; nested, it becomes "repeat this block in every connector and
  keep them in sync forever".
- **Pseudo-platforms have no block.** `__cron__` and `__heartbeat__` arrive with a
  `channel_id` and drive real turns, but there is no `channels.__cron__` section to
  put a scope in.
- **Permissions would split.** `permissions:` is top-level. Permission rules under
  `channels.slack` means the answer to "what may happen here" lives in two places.

The principled split: `channels.<platform>` holds properties **of the connector** —
credentials, `enabled`, defaults. `scopes` holds rules **about requests**, which
may not mention a platform at all.

The cost is locality: reading `channels.slack` no longer shows the whole Slack
story. Mitigated by every scope carrying `channel: slack` in its match (greppable),
and more usefully by the resolver CLI in §12.

## 3. Schema

```yaml
scopes:
  - match:
      channel: slack               # platform
      chat:    C0BKHE3AH4M         # conversation within it
      user:    [U0BLHQQBCCD]       # sender(s)
      role:    admin               # or a named set of people
      not:     {user: [...], role: ...}
    delivery:    {mode: [mention, +has_file], mid_turn: steer,
                  prompt: "...", prompt_append: "..."}
    agent:       {model_name: ...}
    permissions: {tools: {bash: deny}}
```

Three sections, three readers, one match:

| section | acted on by | when | keys today |
| --- | --- | --- | --- |
| `delivery` | the connector | inbound, deciding whether and how to answer | `mode`, `prompt`, `prompt_append` (`mid_turn` is §3.3's design, not yet a key) |
| `agent` | the runtime | building the turn | `model_name` |
| `permissions` | the permission engine | before every tool call | `tools`, on `channel`/`chat` only — the `user` axis still waits on §8.4 |

A scope carrying only `delivery` does not touch permissions. Sections are
independent and each opts in.

### 3.1 Which section a key belongs to (D14)

The column above says **acted on**, not *read*, and the difference is the whole
rule. Every key in every section is *resolved* in whichever process reads the
config, and today that is the gateway for both of the sections that are read at
all, because the gateway is where `channels.slack` is loaded. If reading decided
the section, every key a connector touches would be `delivery` and the split would
say nothing.

What separates them is **carry versus consume**:

- The connector **consumes** `mode`. It decides whether a message is picked up at
  all, and no trace of it leaves the connector.
- The connector **consumes** `prompt`. It is spliced into the message text —
  appended after the user's own words, behind a trigger label, and skipped when it
  is already present — and then it is gone. Nothing named `prompt` crosses the
  wire; the runtime sees a slightly longer user message and cannot tell which part
  the operator wrote.
- The connector only **carries** `model_name`. It validates it, then sets
  `params["model_name"]` on the request and does nothing else with it. The runtime
  is what picks a model. So it is `agent`, even though not one line of runtime code
  reads a scope.

The test is therefore: *if this key stopped being resolved here and were resolved
by the other process instead, would anything about its meaning change?* For
`model_name`, no — only the plumbing. For `prompt` and `mode`, yes; there would be
nothing left for them to act on.

**D14 says where a key goes, not that it can be a key at all.** There is a second
test, and it is the one `work_mode` fails. `work_mode` passes D14 cleanly: a
connector would only put it on `params["work_mode"]`, and the runtime is what acts
on it — `resolve_agent_request_mode` folds `agent` into `code.normal` when it is
`code`. But it is not a per-turn setting. `sync_session_request_metadata` writes it
into a session's metadata the first time it sees that session and never overwrites
it afterwards, so that a session cannot change which project it belongs to halfway
through; `tests/unit_tests/test_work_mode.py::TestSessionMetadataWorkMode::test_update_first_lock_and_repair`
pins exactly that. A scope setting it would therefore apply to conversations that
have not spoken yet and be ignored, silently and permanently, for every one that
has — and Slack keys a session on the thread in a channel and on the person in a
DM, so the conversations already in use would never pick it up at all. There is
nothing to hang the warn-and-drop idiom on either: the lock lives in the runtime
process's session metadata and the connector resolving the scope cannot see it. So
the key is refused rather than shipped half-honoured, and the refusal is written
into the `scopes:` template block beside the reasoning level, which is refused for
the analogous reason — a setting that is fixed somewhere earlier than a request.

**One consequence, written down so it is not mistaken for a bug.**
`_channel_model_name` in `slack_connect.py` re-validates the settled model against
`models.defaults` **at message time**, not at load, because the WebUI rewrites the
model list at runtime through `models.replace_all` and nothing reloads the Slack
channel when it does. That re-check is connector-side and **stays** connector-side.
It is not the connector acting on the model; it is the connector deciding whether
to put a name on the wire that the adapter would silently replace with its default.
Moving it into the runtime "because `model_name` is an `agent` key" would move it
away from the fact it depends on and lose the only warning that failure ever emits.

### 3.2 `delivery.prompt` is not a system prompt

Worth stating plainly, because the name invites the wrong reading and the
difference decides which section it lives in.

`delivery.prompt` is **text appended to the user's message**. It:

- is **visible in the transcript** — the operator's instruction and the user's
  words arrive as one message, and anyone reading the channel sees both;
- is **arguable** — anything else in that message can contradict it, and the model
  weighs the two the way it weighs any two sentences from the same speaker;
- is **attributable to nobody** — once appended it is indistinguishable from
  something the user typed, which is also why it is skipped when the same text is
  already there.

That is a delivery concern: it changes what this connector sends, not how the turn
is built. A standing instruction that must outrank the user is a different thing
with different failure modes, and giving both the same name would be the kind of
collision an operator discovers by being disobeyed.

So **`agent.system_prompt` is reserved** for that different thing: text injected
when the turn is built, ranked above the user's message rather than beside it, and
never rendered as part of what the user said. Nothing implements it and this design
does not propose it now; the name is claimed so that the two can never be written as
one key, and so that a later reader does not find `agent.prompt` and assume it means
whatever `delivery.prompt` means.

### 3.3 `delivery.mid_turn` — a message that arrives while a turn is running

Today every ordinary `chat.send` **cancels** the turn already running on that session
before starting its own. That is deliberate and predates the Goal work
(`_should_cancel_existing_stream_before_chat_send`, whose four carve-outs are
exemptions from a default rather than the mechanism); the stated motive is avoiding
"会话孤岛", a session left running with nobody reading it. It is also often what a user
wants: the dominant reason someone types while the agent is working is to stop it, and
the cancel path SIGKILLs child shells, so it is what halts a runaway tool.

But Slack has **one gesture for two intents** (§8.5, Step 5): posting a message is the
only ambient action, so "stop, this is wrong" and "here is one more detail" arrive
identically and are resolved identically. `mid_turn` is where a conversation says which
of the two its traffic mostly is.

```yaml
delivery:
  mode: [mention]        # which messages are picked up
  mid_turn: cancel       # cancel | steer | queue
```

| value | what happens | mechanism |
| --- | --- | --- |
| `cancel` | the running turn is killed, the new message starts a fresh one | today's default |
| `steer` | the text joins the running round before its next model call | `InputDispatchMode.STEER` → `enqueue_steer` |
| `queue` | the connector holds the message and dispatches it once the turn ends | the pattern the web UI ships |

Each value names a mechanism a reader can grep for, which is why they are not
grammatically parallel — `cancel` and `steer` act on the running turn, `queue` acts on
the new message. `join` / `wait` were considered and rejected: in concurrency
vocabulary `join` *means* wait, so the pair reads as synonyms while behaving as
opposites.

**Why `delivery` and not the runtime section.** D14 asks who *acts*, and for all three
values that is the connector: it checks whether a turn is live, then sends normally,
sends a steer, or sends nothing at all. Under `queue` the message never leaves the
connector, so there is nothing for another process to act on. The name is `mid_turn`
rather than `mode` because `delivery.mode` is already the trigger set, and because
`agent.*` is a live mode-string namespace (`agent`, `agent.fast`, `agent.plan`,
`agent.work.plan`) that a key named `agent.mode` would appear to belong to.

**The connector decides, and it already has the signal.** `turn_initiator(session_id)`
is opened at dispatch and closed by that turn's terminal event, so a non-`None` entry
is "a turn is in flight here". Under `mid_turn: steer` the connector sends an ordinary
`chat.send` when no turn is running and a steer only when one is, which keeps the idle
path on the normal one-request-one-stream shape.

**A steer must not touch the initiator record.** Steering someone's turn is
contributing to their work, not starting your own, so the entry stays with whoever
started it. That is also the right answer for D15: A keeps the stop floor on a turn B
steered.

**One prerequisite, here in the connector.** A steer's own request returns
`runtime.accepted` and a terminal immediately, because the running turn holds the
interaction's output lease and `attach_output` returns `None` to the second caller.
The connector must not read that terminal as "the turn ended": today it would clear
the initiator entry while the work continues, leaving a live turn with no recorded
owner — the state the record exists to prevent. This has to be fixed before `steer`
is selectable.

**One hardening, in the layer below, and not a prerequisite.** A steer sent with no
active round does not fail — it falls through and is pushed as a **follow-up** work
item. The connector's liveness check (`turn_initiator`) is one round-trip stale, so a
round ending in that window selects a mode nobody chose. That window is narrower than
it first appears, because the lease is released in the request generator's `finally`:

- the turn ended and the generator finished, so the lease is free — `attach_output`
  **succeeds**, the request becomes the reader, and the message runs as its own round
  on its own stream. That is the fallback the connector wanted, reached without it;
- the round ended but the generator has not torn down, or a goal holds the lease —
  `attach_output` returns `None`, and the answer is emitted on the other stream.

Only the second case misbehaves. Refusing a steer with no active round would close it
(there is precedent one line above: *"active interaction round cannot accept steer
without loop_controller"*), but that refusal lives in the runtime, and `mid_turn` does
not wait on it.

**`follow_up` is deliberately absent.** It creates a second round whose answer is
emitted on the *first* request's stream under the first request's id, so a connector
whose stream bookkeeping is request-id-shaped would have to demultiplex one stream
carrying two answers. It also raises a question the other three values do not: a
follow-up round is genuinely its author's work, so a single-valued initiator record
becomes wrong and "who may stop this" needs a set or a per-round record — which widens
the D15 floor and therefore narrows what `clicks.stop` can restrict. Both problems are
artifacts of follow-up specifically; `queue` reaches a similar place by giving each
message its own turn, its own id and its own initiator. Adopting `follow_up` should
therefore be an explicit decision that reopens both.

### 3.4 Why the runtime-facing section is called `agent` (D17)

`agent:` is not a free name here. `config.yaml` already uses it twice for the
**mode** — `modes.agent` (against `code` and `team`) and `debug_trace.agent`, whose
comment names `agent.plan` / `agent.fast` — and mode strings are a dotted namespace
(`agent`, `agent.fast`, `agent.plan`, `agent.work.plan`) that a key written
`agent.<x>` appears to belong to. `agents:` and `subagents:` are two further senses.
`scopes[].agent` is a fifth.

`runtime` and `answer` were both weighed. `runtime` matches D14's own wording — *the
runtime is what picks a model* — but names the process rather than the thing being
configured. `answer` pairs neatly with `delivery` as *how the reply is produced*
against *how it arrives and leaves*.

What settles it is the section's likely contents, not the collision. It holds or
reserves three keys, and they are the three fields an agent definition takes:

| key | status |
| --- | --- |
| `model_name` | shipped |
| `system_prompt` | reserved, §3.2 |
| `skills` | not proposed; the obvious next one |

`answer.system_prompt` and `answer.skills` both read wrong: a system prompt and a
skill set are properties of the agent, not of the answer. `agent.*` reads correctly
for all three, and §3.2 has already claimed `agent.system_prompt` under that name. So
the section is the **per-conversation slice of an agent definition**, and the
vocabulary for that already ships: `agents.<name>.model` and `agents.<name>.skills`
configure the same three fields for a reusable template. That block is referenced
only from the team paths today, which makes it a precedent for the naming rather than
a mechanism to reuse.

**One shape note, so the divergence is deliberate.** `agents.<name>.model` is a nested
block carrying `model_client_config` — `api_base`, `api_key`, `custom_headers`.
`agent.model_name` is deliberately *not* that: it is a string naming an entry under
`models.defaults`, validated against the catalogue, so a per-conversation rule cannot
carry a credential and cannot name a model nobody configured. A future `skills` should
match `agents.<name>.skills` in shape — a list of names — because nothing about a list
of skill names invites the same problem.

## 4. Matching

### 4.1 Shape

```
match     = channel? ∧ chat? ∧ identity?
identity  = sender ∈ (user ∪ role) ∖ not.(user ∪ role)
```

Different axes AND. An absent axis matches anything. An absent positive identity
means everyone; an absent `not` excludes nobody.

### 4.2 `user` and `role` are one axis (D5)

They OR, because a role resolves to a set of `(platform, id)` pairs — which is
exactly what `user` enumerates. `role` is sugar over `user`, not a second
dimension.

```yaml
match: {chat: C0_ops, user: [U_oncall], role: admin}
# → in C0_ops, for U_oncall OR anyone in admin
```

AND would mean "U_oncall, but only if also an admin", which nobody wants and which
a config author would write by accident.

`user` accepts a list, so promoting an inline list to a role is a pure refactor.
Both spellings stay: a role of one is ceremony, and starting with raw ids and
introducing roles when repetition appears is the natural path. A lint — not a rule
— can suggest a role when the same id appears in three or more scopes.

### 4.3 `not`, and why there is no `override:` (D4)

The motivating case is "read-only except for admins". The obvious design is an
escalation directive: a more specific scope that *loosens*. It is not in v1.

**Not because escalation is unsound — upstream already does it.**
`permissions.approval_overrides` is a persisted rule list that short-circuits to ALLOW
ahead of the tiered decision, and jiuwenswarm PR #3610's session layer may add `allow`
where neither of its outer layers tightened. An argument that loosening is
categorically wrong would be refuted by the engine this design plugs into.

The narrower claim is the true one: **a mechanism that only tightens is cheaper to
reason about and cheaper to review.** Composition stays order-independent, `strictest()`
remains the only merge, and "can this person run bash here" is answered by finding the
deny rules that match them rather than by reading the whole file for a later exemption.
That is worth the restriction for a v1 whose job is to make restriction possible at all.

**It forecloses nothing.** Adding `override:` later is purely additive: every config
written against v1 keeps its meaning, because no existing scope loosens. If the case
for escalation is made — by us or by anyone else — it is a later decision taken on its
own merits, not one this design has spent.

With negative matching, the exemption is written into the rule it exempts from:

```yaml
- match: {channel: slack, chat: C0_readonly, not: {role: admin}}
  permissions: {tools: {bash: deny, write_file: deny}}
```

An admin in that channel matches no restricting scope and keeps whatever the
ceiling gives them.

`{role: team, not: {user: [U_intern]}}` — the team minus one — is the case that
justifies allowing a positive and a negative together. Without it, that requires
enumerating the team minus one, which rots when the team changes.

### 4.4 `not` is identity-only in v1 (D6)

`not: {chat: [...]}` — "every channel except these" — is tempting and deferred. It
raises a question that need not be answered yet: does `not: {chat: A, user: B}`
mean *not (A and B)* or *(not A) and (not B)*? Channel lists are short; write them
out. The syntax stays forward-compatible for either reading, and for a list of
`not` objects.

## 5. Composition (D2)

Rules follow the value's **type**. This is easier to remember than per-key rules
and it generalises to keys that do not exist yet.

### 5.1 Scalars — replace

`agent.model_name`, and anything else single-valued. Last matching layer wins.

### 5.2 Sets — replace by default, with explicit mutation

```yaml
- match: {channel: slack}
  delivery: {mode: [mention]}
- match: {channel: slack, chat: foo}
  delivery: {mode: [+has_file]}     # mention AND has_file
- match: {channel: slack, chat: bar}
  delivery: {mode: [all]}           # replaces entirely
- match: {channel: slack, chat: baz}
  delivery: {mode: [-mention]}      # inherit, minus mention
```

Union-only would make a trigger unremovable; replace-only would force restating the
base to add one. Both are needed.

**Validation:** a list is either all-plain or all-signed. `[mention, +has_file]` is
rejected — it reads as either and would mean whichever the implementation happens
to do.

### 5.3 Prose — replace, with a separate append key

`prompt` replaces. `prompt_append` appends to whatever the layer above set. A
sigil inside a multi-line prose block would be miserable to read and worse to
escape, so this is two keys rather than a marker.

**`_append` is a layering operator and means nothing else.** It says "add to the
value the layer below settled" — the alternative to restating a paragraph in order
to add a sentence to it — and it would mean exactly that on any prose key in any
section. It is not a statement about where the value ends up.

That is worth separating because `delivery.prompt` happens to be appended to
something *else* as well: §3.2's appending to the user's message. The two are
unrelated. One is how two config layers combine into one value; the other is what
this connector does with the value once it has it. A key that composed by
`_append` and were injected at the head of a turn would be no contradiction, and
reading the suffix as "this text goes at the end" would make `mode_append` sound
meaningful, which it is not — sets have signs instead (§5.2).

### 5.4 Maps — per-key merge (D3)

`permissions.tools` merges per key; the *values* narrow via `strictest()`. So a
platform scope setting `{bash: ask}` and a channel scope setting `{write_file: deny}`
both apply.

**`permissions` composes order-independently. `agent` and `delivery` do not.**

That asymmetry is deliberate: a security property must not depend on file order,
while configuration naturally cascades. To keep the ordered half safe, **warn at
load when a more general scope follows a more specific one it would override** —
that is almost always an authoring mistake rather than intent.

## 6. Layers

Per key, later wins — with `channels.<platform>` as layer 0 of the same cascade:

```
layer 0   channels.<platform>.*              connector defaults
layer 1   scope {channel: X}
layer 2   scope {channel: X, chat: Y}
layer 3   scope {channel: X, chat: Y, user: Z}
layer 4   a cron job's own fields             wins when set
```

A platform-only scope is not a special case — it is the first override layer. It is
legal but usually redundant with layer 0, so **warn when a scope sets a key the
connector block already sets**: two places to look for one value is an authoring
slip.

This also gives the deprecation path for free. Once `scopes` is validated, layer 0
shrinks to credentials, `enabled`, and the two retained upstream gates; everything
behavioural moves up.

Per-key layering matters, and it is per key across sections as well as within one.
Without it, a channel scope overriding only the prompt would have to restate the
model — the duplication a single flat per-channel entry forces. The sections are
folded separately and neither seeds the other, so a scope naming only `agent` keeps
whatever `delivery` the layers below settled, and the reverse.

## 7. Capabilities and opt-in (D7)

Applicability is a property of the implementation, not a deployment choice. An
operator cannot make a connector support an axis it does not populate, and letting
them declare one moves the failure from a load-time warning to silent
non-matching.

```python
@dataclass(frozen=True)
class ChannelCapabilities:
    axes:          frozenset[str]                       # {"channel", "chat", "user"}
    sections:      dict[str, frozenset[str] | None]     # section → allowed keys; None = all
    attended:      bool                                 # can a human answer an approval?
    identity_keys: tuple[str, ...]                      # ordered; first present is canonical
```

```
slack      axes {channel, chat, user}   {delivery: {mode, prompt},
                                         agent: {model_name},
                                         permissions: all}                attended=True    ids ("user",)
feishu     axes {channel, chat, user}   sections all                      attended=True    ids ("open_id", "union_id")
web        axes {channel}               sections all                      attended=True    ids ()
__cron__   axes {channel}               {permissions: all,
                                         agent: {model_name}}             attended=False   ids ()
```

Slack's row is the one that is real; the rest are the shape, not the code. It names
its keys rather than declaring `sections all` for the reason §3.1 gives: `mode` and
`prompt` are things it consumes and `model_name` is a thing it carries, so a scope
that writes `delivery: {model_name: …}` is told which section the key lives in
instead of being obeyed in a section that does not own it. `__cron__` is listed
with both sections as the design intends (§9.4); of the two, only `permissions`
is shipped — it is resolved generically at every runtime entry point regardless
of connector, so cron already gets it. `agent` stays sectionless, because
nothing resolves scopes for cron's own conversation yet and declaring the
section would promise a resolution no code performs.

**`attended=True` is, upstream, true of no IM connector.** Grepping `im_platforms/`
on `upstream/develop` for permission rendering returns nothing:
`_request_permission_confirmation` returns `"interrupt"` for everything except `acp`,
which is exactly why `owner_scopes` degrades ask→deny today. Our branch has interactive
Slack approvals; upstream does not. The table above therefore describes **a capability
of the deployment, declared by the connector that has it** — which is precisely why
§7.2 makes the declaration the opt-in rather than reading a boolean from config. A
connector that cannot render an approval declares `attended=False` and gets D11's
degrade; nothing needs to know why.

### 7.1 Where it lives

`common/`, as a static registry. Both processes import the same package, so the
gateway and the runtime see identical capabilities with nothing crossing the wire.
Connectors declare theirs as a class attribute; pseudo-channels get module-level
entries, having no connector to hang it on.

Which process *resolves* a section is not the same question as which one acts on it
(§3.1) and does not track it. Today the gateway resolves `delivery` **and** `agent`,
because `channels.slack` is loaded there and `agent` currently holds one key the
connector was already settling; `permissions` is resolved where it is enforced — the
runtime, at every tool call (§11 Step 3). A shared registry is what makes that safe
to change later: moving the resolution of a section from one process to the other
alters no declaration and no scope.

### 7.2 Opt-in is the declaration

There is no separate boolean. **No declaration means not opted in**, and scopes
naming that channel warn as inert. A connector adopts `scopes` by declaring what it
supports — one edit, in the file that already knows the answer — and validation
comes from the same mechanism rather than being bolted on.

Three warning classes fall out:

- scope names an unknown channel
- scope uses an axis the channel cannot populate — *"will never match"*
- scope sets a section or key the channel ignores — *"has no effect"*

All are **warnings, never failures**, consistent with how the connector already
handles a bad mode or an unknown model, and with the principle that a config
mistake must not take the service down.

### 7.3 `attended` (D11)

An `ask` reaching an unattended channel is a turn that waits for a click nobody
will make. `attended=False` degrades `ask` to `deny`.

Precedent exists: `check_avatar_permission` already does this, documented as
*"返回 allow 或 deny（ASK 自动降级为 DENY）"*. Fail-closed is the right direction, and
it makes the failure legible — a cron job that hits a restricted tool errors with a
reason instead of vanishing into a timeout.

Pair with a load-time warning when a scope could produce `ask` for an unattended
channel: the author probably meant `allow` or `deny`.

**Built as `_degrade_unattended` in `jiuwenswarm/common/scopes/permissions.py`,
narrower than the paragraph above reads on its own.** It fires only where the
channel's capability has *declared* `attended=False` (§7.2's opt-in) — a channel
with no declaration is left alone, not assumed unattended. And it degrades only
the levels a matching `permissions` scope itself narrows to; the base permission
config's own `ask` (what a tool resolves to with `scopes: []`) is never touched,
because degrading that would change what every job on that channel already does
today, attended or not — a larger decision than this section.

**The consequence, which is D11's own failure mode on the path D11 does not
cover.** A scheduled turn that reaches a tool the *base* config marks `ask` waits
for a click nobody can give: `__cron__` renders no buttons and has no reader. That
is precisely what D11 exists to prevent, and the degrade does not reach it.

No scope can close it either. `allow` in a scope is a no-op — it folds to
`strictest(base, allow) == base`, because v1 tightens only (D4) — so a scope
cannot grant a scheduled job the freedom to run. The only level a `permissions`
scope can meaningfully set on `__cron__` is `deny`, which converts a hang into a
clean refusal: worse than running, better than stuck, and the only one of the
three expressible today.

It is **dormant while `permissions.enabled` is `false`** (the shipped default, and
the current live setting) and **armed the moment it is not** — at which point
`bash: ask`, `write_file: ask` and their siblings in the base config each become a
way for a cron job to stop dead.

Three ways out, in ascending order of blast radius: ship a `__cron__` scope denying
those tools, so a job fails with a reason rather than hanging; set them `allow` in
the base config, which gives up the gate everywhere rather than on cron; or extend
the degrade to the base config on channels that have *declared* `attended=False`,
which is the one that matches D11's stated intent and is also the behaviour change
the paragraph above declined to make. Deciding it needs someone to weigh a real
change to existing jobs against a hang that is currently invisible because the
engine is off.

## 8. Identity

### 8.1 An opaque bag (D9)

`{channel, user}` bakes in an assumption that does not hold. Slack needs `user`
*and* `team`; Feishu has three ids for one person; web has none; a2a and acp never
set a sender at all.

```json
{"channel": "slack",  "user": "U0BLHQQBCCD", "team": "T0BKJQBQ1AN"}
{"channel": "feishu", "open_id": "ou_…", "union_id": "on_…"}
{"channel": "web"}
```

`channel` is always present — that is jiuwenswarm's own axis. Everything else is
channel-defined and **opaque to the core**, which never looks inside. That keeps
the shared schema honest: one field, one type, no per-channel subfields creeping
into a common model.

`identity_keys` says which key is canonical for matching, ordered — so Feishu
accepts either id for the same person without the config author knowing which one
the event carried. `identity_keys = ()` makes the `user` axis unavailable, which
must agree with the `axes` declaration; validation cross-checks them.

This is also the generic form of the current mess, where each connector writes its
own `slack_user_id` / `slack_team_id` keys into a free-form `metadata` dict that
nothing outside the gateway reads.

**Half of this is already built — reuse it.** `jiuwenswarm/gateway/routing/keys.py`
defines frozen `RoutingKey(user_id, channel_id, app_id, agent_ref, session_id)` whose
docstring reserves the wildcard `'*'` *"为监管等高级场景预留"* — matching, for exactly
this kind of case — plus `IdentityKey(channel_id, app_id, user_id)` and a
`DeliveryTarget` base with per-connector frozen subclasses (`FeishuDeliveryTarget`,
`WecomDeliveryTarget`, …) carrying platform-private id fields alongside a shared
`physical_user_id` and a `container_kind` / `get_container_id()` abstraction. That is
the opaque bag described above, typed and shipping.

The reuse is **partial, and the boundary is the process boundary**:

| section | resolved in | identity source |
| --- | --- | --- |
| `delivery` | gateway | **extend `IdentityKey` / `DeliveryTarget`** — every connector already builds one |
| `agent`, `permissions` | runtime | needs its own bag: `RoutingKey` is imported *only* under `jiuwenswarm/gateway/` and never crosses the WebSocket |

Two gaps to close either way: `RoutingKey` carries `session_id`, not `chat_id`, so the
`chat` axis has no home in it today; and `identity_keys` above stays the runtime-side
answer regardless. Writing a second registry for `delivery` would be the mistake a
reviewer catches first.

### 8.2 `people`

```yaml
people:
  harenome: {slack: U0BLHQQBCCD, feishu: ou_a1b2c3}
  boss:     {slack: U_boss}
```

Identity mapping separated from grouping. Add a platform to a person once and every
role they are in follows.

**Built.** Top-level, a sibling of `scopes:` rather than anything under `channels`,
and that placement is the whole argument for the block: a person is one human with
an id on each platform they are reachable on, so under `channels.slack` the same
human would have a separate identity per connector and "the admins" would mean a
different set of people on each — the thing roles exist to remove.

**One refinement the implementation made.** The value under a platform is an id
*or a list of them*. §8.1 has Feishu carrying three ids for one person, and what
reaches the matcher is one string — whichever of the platform's `identity_keys` the
event happened to carry. Listing both is the only shape that can be honoured today:
a map keyed by `identity_key` reads better and would need the matcher to know which
key the sender came from, and it is handed a sender rather than a bag.

A platform key nobody has declared is *not* warned about. A directory of humans
legitimately carries ids for platforms a deployment does not run, and a config
shared between two deployments always will. The warning an operator can act on is
emitted where it is actionable instead — on the scope, when a role it names resolves
to nobody on the channel that scope is written for.

### 8.3 `roles` (D8)

```yaml
roles:
  admin: [harenome, boss]
```

A named set of people. **No `tools:`, no permissions, no grants.** All authority
stays in `scopes`, so there remains exactly one place to answer "what can happen
here", and no role definition can quietly raise a ceiling.

The conventional RBAC shape — `admin: {tools: {"*": allow}}` — does the opposite:
authority in two places, and the escalation problem that §4.3 removed comes back.

**Fail-closed rules:**

- an unknown or empty role matches nobody, so `not: {role: admin}` matches
  *everyone* — the restriction applies universally rather than being silently
  disabled. Warn at load, because a typo would otherwise lock out the people it was
  meant to exempt.
- a person with no id for the current platform is not in the role there, so
  `not: {role: admin}` does match them. Restrictions apply on platforms where they
  have not been identified.

**The first of those two shipped differently, and the difference is deliberate.**
The second is implemented exactly as written and falls out for free: a role is
resolved per platform, a member with no id there contributes none, and the
restriction applies to them. It is bit for bit the answer the `user` axis already
gives for a sender the connector could not name.

The first was split in two, because it conflates a config that *can* be honoured
with one that cannot:

- a **declared** role whose members simply have no id on this platform is
  honourable, and its answer is the bullet as written: the positive half matches
  nobody, the negative half excludes nobody, the restriction applies universally,
  and both directions are warned about by name.
- a role name that **no `roles:` block declares** — a typo, or a role deleted from
  under a rule still using it — is refused: the whole scope is dropped, which leaves
  that conversation on the layer below.

Reading the undeclared name as "nobody" is what the bullet's own warning text is
worried about, and refusing it is what §4.4 and `_compile_ids` already do for every
other unreadable criterion in a `match` — *dropping reaches less far than what was
written*. It is also what Step 2 shipped for `role` while the axis was deferred, and
one axis may not have two answers. The cost is stated in the warning rather than
hidden: a dropped restricting scope means the restriction is **not applied**, so an
unknown-role warning is worth reading rather than worth filing.

A `roles:` entry naming somebody who is not in `people:` is refused the same way,
and takes the whole role with it rather than one name. A role quietly missing a
member would apply a restriction to exactly the person a `not: {role: admin}` was
written to exempt, and it would do so invisibly.

A role on a channel that does not identify a sender is **warned** about, not
dropped, and warned in the spelling the author wrote. That is the channel failing to
fill an axis rather than a config that cannot be read; it is what §7's capability
check already reports for every other spelling of every other axis; and `user` and
`role` are one axis (D5), so giving one spelling a refusal where the other gets a
warning would be a second answer to one question.

**Roles are not the avatar principal.** `owner_scopes`' `principal_user_id` is who
the bot *is* — `channels.<platform>.my_user_id`, one per connector, bounding what
the bot may do in that person's name. A role is about who is *asking*. They never
interact and must not share a config key. `owner_scopes` is unchanged by this design.

**Why not simply extend `owner_scopes`.** It must be answered directly, because from
the outside it looks like the same thing: it is a live `{channel: {user: {tools}}}` map,
it is not confined to the digital-avatar path — `interrupt_helpers.py` falls through
past the avatar branch into a *generic* branch that reads
`owner_scopes[channel_id][principal_user_id]` for any scene, gated only on both ids
being non-empty — and it has a Web UI editor (`AvatarPermEditor.tsx`) with config
writers behind it. Three reasons:

1. **The subject differs.** Its key is the principal the bot impersonates; ours is the
   sender. Same shape, opposite meaning. One map holding both would answer
   "whose authority is this" differently depending on which branch reached it.
2. **The ambiguity is concrete, not hypothetical.** That fallthrough already resolves
   two meanings by *ordering* — avatar first, generic second. Adding asker-scoped rules
   to the same map makes a third, and "which branch wins" stops being readable from the
   config. A separate key keeps the precedence question inside §8.3 where it is written
   down, instead of inside a closure's control flow.
3. **It is single-principal by construction.** `my_user_id` is one value per connector.
   The asker axis is inherently many-valued and needs `people` / `roles` behind it;
   bolting that onto a map keyed by a single principal would fork its semantics anyway.

The honest cost: `owner_scopes` keeps its own editor and its own storage, so an operator
has two places to look. That is the price of the two questions being different, and it
is the reason the resolver in §12 matters more than config locality (§2.3).

### 8.4 Identity: what arrived, and what did not

An earlier draft made the one-line `agent_compat.py` fix a prerequisite of this design.
**It is merged** — `403fe354a`, upstream `develop`, 2026-08-24 — for unrelated reasons
(the AgentOS multi-user refactor). The chain is whole: `slack_connect.py` sets
`Message.user_id` from `event["user"]` → `gateway_normalize.message_to_e2a` carries
`user_id` and `chat_id` → `agent_compat` → `AgentRequest.user_id`. Nothing here is
blocked on plumbing any more.

Three qualifications survive, and each is a design constraint rather than a task:

- **`user_id` is overloaded.** Under `agent_client.type=agentos_router` it selects
  `{workspace_root}/{user_id}` and is part of `agent_key_fields`, validated
  `^[a-zA-Z0-9_-]+$` because it becomes a path segment. In that deployment, treating it
  as the IM sender forks a workspace per person. The matcher must therefore read the
  sender from the identity bag (§8.1), *not* assume `AgentRequest.user_id` is it.
- **Coverage is partial.** `Message.user_id` holds the true sender only for **Slack,
  Feishu and SSH**; DingTalk, WeCom, WeChat, WhatsApp, Telegram, Discord and A2A leave
  it in metadata. The upstream idiom is `msg.user_id or meta.get("im_sender_user_id", "")`
  (`message_handler/join_exit_handlers.py`). This is exactly what §7's `identity_keys`
  and the per-channel `axes` declaration exist to express — a connector that does not
  populate a sender does not declare the `user` axis, and scopes naming it warn as inert.
- **Identity is not authorization, and upstream says so.** The refactor states
  `user_id 只用于路由/观测关联`, and `gateway_adapter/base.py` forbids deriving directories
  from it. There is no user table, no `tenant_id`, no session-per-user model on
  `develop`; where upstream wants *authenticated* identity it comes from the AgentOS
  external IAM (`auth_service_url`, `/api/v1/auth/verify`, off by default). So `scopes`
  cannot lean on an existing identity model — but neither is it colliding with one.

**On `PermissionContext`.** An earlier draft proposed populating the typed
`PermissionContext` in `common/schema/agent.py` so the field has one writer. That field
exists and is never populated, but `owner_scopes.py` defines a *second*
`PermissionContext` whose docstring records the opposite decision verbatim —
*不放入 schema/agent.py，不序列化到 AgentRequest；仅从 metadata 构建 → ContextVar → 匹配*.
That is a written-down upstream position, not an oversight, and PR #3610 edits that same
file. Keep the requirement — **the sender must have exactly one writer, because a role
system keyed on a value a prompt could influence is decorative** — and settle the
mechanism against #3610 rather than against the empty typed field.

### 8.5 Interaction authorization (D13)

Everything above authorizes a **turn**: a sender says something, and `delivery`,
`agent` and `permissions` decide what that may cause. A **click** is not a turn. It
arrives against a turn that already exists, from someone who may not have started
it, and it carries its own principal.

Two clicks exist today or are wanted:

- **Approval buttons.** Live on this branch. An `ask` renders as Block Kit, and in a
  deployment that sets no `allow_from` *anyone in the conversation can click approve*.
  The click carries a `user` and `_handle_question_action` does now read it, for
  exactly one purpose: layer 0's `allow_from` (D10). That is a membership list, not a
  per-conversation rule, and it is empty by default — so the gap is narrower than an
  earlier draft of this section claimed, and it is still the security-relevant click,
  because the click is the gate on a tool call the agent was told to stop at.
- **A stop button.** Built: a `danger`-styled Stop button on the turn activity card
  (`action_id` `jiuwenswarm_stop`), with its own Bolt listener registered outside
  `_QUESTION_ACTION_ID_RE` — a stop is not an answer to a pending question, and the
  two listeners refuse different things. `_may_stop` (`slack_connect.py`) enforces
  D15's floor first — the recorded initiator may always stop their own turn — and
  falls back to F1's `allow_from` check otherwise. It dispatches the same
  `ReqMethod.CHAT_CANCEL` (`"chat.interrupt"`) that Web, CLI, TUI and ACP already
  send. Its failure mode is still mild — a wrongly permitted stop wastes work
  rather than causing any — which is why D15 can afford a floor here that
  `approve` does not get.

**The decision: a click is authorized like a sender.** It reuses §8.1's identity bag
and §8.3's roles, matched on the same axes, rather than growing a second principal
model beside them. A click's `user` comes from the platform payload and never from
model output, so it satisfies §8.4's requirement — *the sender must have exactly one
writer* — more cleanly than a message does.

**But it is a separate consumer, not a free consequence of Steps 2-4.** Those steps
give the matcher a `user` axis and give the config `people` and `roles`. Nothing in
them reaches the connector code handling a `block_actions` payload. The work is to
read the clicker out of that payload, build the same identity bag, and match it — in
a place that has no `AgentRequest` and no turn to hang off.

**Shape, when it is built.** A `clicks` key alongside `delivery`, read by the
connector at click time rather than at turn build:

```yaml
scopes:
  - match: {channel: slack, chat: C0BKHE3AH4M}
    clicks:
      approve: {role: operator}       # who may answer a permission ask
      stop:    {role: [operator, member]}
```

Composition is §5's, unchanged — a map merging per key. Absent means whatever layer 0
already decided, which is F1 below. **Tightens only** (D4), so a `clicks` rule can
never widen a channel that was already restricted.

**Built, and four things the shape above did not settle.**

- **What "a map merging per key" merges.** The `clicks` map merges per *gesture*, so
  a conversation that narrows `stop` keeps the `approve` settled above it. A clause
  is one settled value and a later layer *replaces* it. Merging the halves of a
  clause instead would leave a narrower rule able only to add people, which is the
  direction D4 forbids of the one section written to tighten — `{role: operator}`
  under `{role: member}` has to be able to mean fewer people, not both sets.
- **A clause names people the way a `match` does**, `user` and `role`, and the two OR
  (D5). Roles resolve to ids per platform at load, exactly as §8.3 resolves one in a
  match. `not` is **not** offered: "anyone but these people may approve" is the
  permissive default `clicks` exists to close, written the long way round, and §4.4
  leaves `not` on a second axis open rather than answered.
- **A rule that also names a sender cannot carry a `clicks` section.** A match's
  identity axis names whoever sent a *message*; a clause names whoever pressed a
  *button*, and a click has no turn behind it to read the first from. Left standing
  such a rule would be settled for nobody — inert, silently, in the one section
  written to restrict — so it is reported and the section dropped. Who may click is a
  property of the conversation.
- **`clicks` is not a connector section**, so naming a conversation in a `clicks`
  rule does not opt it into being answered. That is the security property
  `permissions` already has (`scoped_chats`): on Slack those ids are what exempts a
  channel from `allowed_channel_ids`, and a rule written to take something away must
  not hand something else out.

**Two failures that look alike at load and are not.** A clause that cannot be *read*
— a typo, an undeclared role name, a shape that is not a mapping of people — is
dropped, and the click falls back to F1. That is a widening, and every warning says
so, because refusing every click over a misspelling would take a deployment's
approvals away for a mistake the same warning tells it how to fix; the mistake is
loud at load and costs nothing to correct. A clause that reads perfectly and settles
to *nobody* — a declared role whose members have no id here — is kept, and refuses.
That is F2, it is silent at load and only fails at the click, and it is the case the
permissive reading would erase.

**Three constraints inherited rather than new.**

- Coverage is §8.4's. A connector that does not populate a sender does not declare
  the `user` axis. Slack, the only IM connector rendering interactive approvals on
  this branch (§7), does populate it. What a `clicks` rule does on a channel that
  *renders* clicks without naming their clicker is not "warns as inert" — an earlier
  draft of this bullet said that, and it is the permissive answer to the question F2
  below settles the other way.
- `owner_scopes` is still untouched (§8.3). It bounds what the bot may do *as* its
  principal; `clicks` bounds who may ask it to. They do not interact.
- The single-writer requirement must be settled against upstream PR #3610, which
  edits `owner_scopes.py`.

#### The floor: what a click may do when nobody can say who clicked

D13 says a click is authorized like a sender. §8.4 says the sender is often not
knowable: `Message.user_id` holds a true sender for three of the connectors listed
there and the rest leave it in metadata, `__cron__` and `__heartbeat__` ship
`identity_keys=()`, and `user_id` is doing a second job under `agentos_router`. So
"identity absent or unusable" is an ordinary case rather than an edge, and D13 is not
implementable until this is written down. Three clauses; F1 describes code that is
running, F2 and F3 are design for Step 5.

**F1 — no `clicks` rule matches: layer 0 decides, and layer 0 is not always
"anyone".** `allow_from` and `allowed_channel_ids` (D10) keep whatever they already
gate, and the Slack click handler enforces the first of them today. The absence of a `clicks` rule
therefore never *removes* a gate; it only declines to add one. It does leave
"everyone in the conversation may approve" standing wherever `allow_from` is unset,
which is the default and is the gap `clicks` exists to close.

**F2 — a `clicks` rule matches and the clicker cannot be identified: refuse the
click.** Unusable means one of two things: the payload carried no value for any of the
channel's `identity_keys`; or it carried one and the rule names a `role` that no
`people:` entry maps that id into. The second is §8.3's second fail-closed bullet read
at click time — *a person with no id for the current platform is not in the role
there* — and the first is the same rule with one fact fewer.

Refusal is the safe direction rather than the permissive one, and the reason is worth
stating because the two directions fail differently. Identity goes missing by
degradation — a payload shape that changed, a connector that never populated the
field (§8.4), an id blanked because it was serving a second purpose — or because
someone arranged for it to. Under a permissive reading each of those quietly converts
a written restriction into no restriction while the config still says otherwise;
under F2 each converts it into a refused click with a logged reason. That is D11's
argument applied to a click instead of an `ask`: fail closed, and make the failure
legible. The cost asymmetry points the same way — a wrongly refused approval stalls a
turn that can be asked again, a wrongly granted one is the tool call the `ask` existed
to stop.

**F3 — the starter's allowance (D15, below) requires a recorded starter.** If the
turn's record carries no initiator, no clicker can claim to be it, and F1 and F2
decide the click alone. That allowance is a right belonging to an identified person,
not a default an unidentified click inherits — otherwise "whoever started it may stop
it" would read, on a payload with no user, as "anyone may stop it".

**What F2 does not cover.** It does not refuse clicks on channels that render none.
`__cron__` and `__heartbeat__` have no buttons, so a `clicks` rule naming them is
inert because there is no click to refuse, which is §7.2's ordinary *"has no effect"*
warning. The distinction to hold onto is between **no surface** and **no identity**:
the first is a scope written against the wrong channel, the second is a scope that
would have applied had the fact it needed arrived.

**And a third case that neither covers: nothing reaches a cron turn at all.** A cron
run does not execute on the conversation it reports into. `_make_execution_context`
in `jiuwenswarm/gateway/cron/scheduler.py` returns `("__cron__",
f"cron_{ts}_{job.id}")`, and the gateway cancels on a `(channel_id, session_id)`
match. A Slack message carries that channel and a `slack_…` session, so it matches
neither field. **A cron turn is not stoppable from Slack today, and never has been**
— not by policy but because no gesture addresses it.

So the categories are three, and only the first two are scope problems: **no surface**
(a rule on a channel that renders no buttons), **no identity** (a rule that would have
applied had the fact arrived), and **no reachability** (a turn no gesture can name).
The third cannot be fixed by writing a better scope, and it is the one that decides
how much of cron belongs in this design at all.

**One discrepancy to close in the connector, not here.** `_handle_question_action`
guards with `if user_id and not self.is_allowed(user_id)`, so a payload carrying no
user id skips the allow-list check rather than failing it. That is the permissive
reading of exactly F2's case, in shipped code. It is unreachable in practice as long
as Slack sends `user` on every `block_actions` payload, and it is a one-line change in
`[connector]` rather than anything scopes owns — recorded here so the next reader of
F2 does not assume the code already agrees with it.

**How F2 interacts with it, now that F2 is code.** The `clicks` check sits below that
guard in the same method and is not written the same way: it applies the rule to the
empty id rather than skipping it. So on a conversation with a `clicks.approve` rule
the payload that guard waves through is refused by the line after it, and on every
conversation without one the guard behaves exactly as it always has. Two consequences
worth naming rather than discovering. The guard is **not** made unreachable — it still
decides alone wherever no rule is written, which is the default — so nothing about it
has been quietly fixed, and the decision it is waiting on is still open. And the two
gates do not agree about the same payload, which is now visible from one screen rather
than inferred: whoever closes the discrepancy is closing an inconsistency between two
adjacent lines, which is an easier argument than the one this paragraph had to make
before. The stop path never had the inconsistency — `_may_stop` applies the allow list
to an empty id — so it needed no equivalent note.

#### Whoever started a turn may stop it (D15)

This was §13's Q5: does a stop carry an implicit *whoever started the turn*
allowance, and if it does, is that hardcoded, a reserved role, or something an
operator has to write? Answered by the operator, 2026-08-31: *"yes, a user who
started should always be able to stop their own turns."*

**The starter's right is a floor, not a grant**, and that distinction is what keeps it
consistent with D4. If `clicks.stop` could confer the right it would be a scope that
widens, which D4 forbids. Read as a floor, the same configuration only ever narrows:

- no `clicks.stop` rule — F1 decides, so whoever layer 0 admits
- `clicks: {stop: {role: operator}}` — narrows that to operators
- the starter is permitted either way; tightening does not reach that floor

**Not a reserved role name, and not settable.** Q5's three options reduce to one once
D4 is applied. *Require it to be written* makes it a grant. A *reserved role* is a
name an operator could shadow in `roles:` and believe they had removed — worse than an
invariant they cannot address at all. So it is invariant, enforced where the click is
handled. §7.2's objection — that this is a principal the config never names — is
answered by writing it down here rather than by making it configurable: what §7.2
rejected was an invisible *switch*, a boolean that changes behaviour without appearing
anywhere near where the behaviour is written. A floor is not a switch. It has one
value, it does not vary by deployment, and no configuration means something different
because of it.

**Affordable for `stop`, and deliberately not offered for `approve`.** A wrongly
permitted stop wastes work rather than causing any, as the stop-button bullet above
says, so the worst a too-generous floor buys is a turn someone has to start again. On
`approve` the same generosity is the gap §8.5 opened with. There is therefore no
starter's allowance on `approve`: starting a turn is no claim to answer what it goes
on to ask.

**What Step 5's first half built.** The allowance needs the turn's initiator at
click time, and that is recorded — but deliberately not on the connector's
activity record. It lives in its own map, `_turn_initiators`
(`slack_connect.py`), and `_SlackTurnInitiator`'s docstring gives the reason:
`_SlackActivityRecord` exists only while `activity_card` is on and only for a
turn that did tracked work, and *"a fact about who may stop a turn must not be
contingent on a display setting."* Recorded at dispatch, read by `_may_stop` via
`turn_initiator(session_id)`; F3 still governs a turn nobody recorded — an entry
that aged out, a session with nothing running — where the floor simply does not
arise and the allow list decides alone. That was connector work, independent of
the scopes half — §11 Step 5.

## 9. Cron

### 9.1 `__cron__` is a real channel

4,102 turns in a week's journal arrive with `channel_id="__cron__"`, alongside
`__heartbeat__`. Both are matchable.

Because scopes only tighten, the working shape is **permissive ceiling, narrow per
channel** — cron inherits the ceiling by matching no restricting scope:

```yaml
permissions:
  defaults: {"*": allow}

scopes:
  - match: {channel: slack}
    permissions: {tools: {bash: ask, write_file: ask}}
  - match: {channel: slack, not: {role: admin}}
    permissions: {tools: {cron_create_job: deny}}
```

Writing it the other way — a restrictive ceiling with a permissive `__cron__`
scope — cannot work, since a scope may not loosen.

### 9.2 Cron is an escalation path (D12)

A restricted user who can create a cron job creates work that later runs under the
permissive cron ceiling rather than their own scope. Denying `cron_create_job` to
non-admins is therefore not incidental, and the reason should be written down or
someone will helpfully allow it back.

General rule: **a restricted principal must not be able to enqueue work that runs
unrestricted.** The same applies to any other deferred execution.

### 9.3 The creator field, and two permission models

**`CronJob` already has one.** `user_id: str = ""` exists on `develop`, documented
*记录创建者标识（web 端 user_id）… 语义=创建者，创建后不可变* and used to fill the faas
`X-Session-Context`. Introducing `created_by` beside it would give one record two
creator fields with no rule for which wins — the §8.3 mistake, in a different file.

So: **widen the existing field, do not add one.** The stored value must become an
identity bag (§8.1) rather than a bare string, because a Slack creator is not addressable
by a web `user_id`; the migration is the usual widening of a scalar to a mapping, with
the bare string read as `{"user": value}` for records already written. Whatever shape it
takes, it stays a declared field:

```python
# jiuwenswarm/gateway/cron/models.py — CronJob
user_id: str | dict[str, str] = ""      # was: str
#   ""                                   never recorded
#   "u_web_123"                          legacy web value, read as {"user": …}
#   {"channel": "slack", "user": "U0…"}  an identity bag (§8.1)
```

Backward-compatible in both directions: `from_dict` and `to_dict` are explicit
field-by-field, so unknown keys are dropped on load and missing keys take the
default. `model_name`, `last_session_id`, `project_id`, `work_mode`, `app_id` and the
`targets` / `CronTargetChannel` enum are all precedents for extending this dataclass.

**It must land in the model before any value is written** — `to_dict` emits only
declared fields, so a hand-edited value would be erased by the next save.

Then `cron.permission_model`:

- `fixed` — the `__cron__` scope decides. Simple, admin-controlled, and leaves the
  escalation path in §9.2 open.
- `creator` — resolve the **stored identity's** scopes at run time. Not a frozen
  permission set: freezing goes stale when someone is demoted. One extra field, no
  staleness, and it composes with the existing rule — match on both `{channel:
  __cron__}` and the creator's identity, narrowing across both. No new field: it reads
  the widened `user_id` above.

A creator identity is worth storing regardless: today "who scheduled this job" is
answerable only for jobs created from the web UI, and not at all in terms that reach
back to the person on Slack.

### 9.4 Section applicability

`delivery` is meaningless for cron — no trigger, no mention, no thread. A scope
setting it warns as ineffective, via the same declaration as everything else in §7.

`agent` is **not** ignored wholesale. A cron job carries its own prompt and model,
but not always — live job records show `"selected_model_id": null`. Treating the
job as layer 4 makes a `__cron__` scope's `agent.model_name` a useful *default* for
jobs that pin nothing, while any job that does pin one is unaffected. No special
case.

`permissions` is now supported, and — unlike `delivery` and `agent` — is resolved
generically at every runtime entry point rather than by connector-specific code
(§7.1), so `__cron__` already declares it (`sections={"permissions": None}` in
`capabilities.py`) and a `__cron__` permissions scope has an effect today. `agent`
is the one thing left to build for cron specifically: `agent.model_name` composes,
but what cron lacks is a resolver of its own, so `__cron__` still declares no
`agent` section — a declaration would say the setting is read, and it is not.

## 10. Related work upstream

Surveyed 2026-08-24 against jiuwenswarm `2cc2048b7` and agent-core `fd6c47854`.

**Nothing upstream blocks this.** `scopes:`, `people:` and `roles:` are free names; no
PR or issue in either repo proposes a top-level policy section; the
`channels.<platform>` loading path in `app_gateway.py` has five commits in its history
and one in the last six months. There is also **no upstream demand signal** — bilingual
searches for per-channel and per-user policy returned no tickets. This is a want of
ours, and should be argued on its merits rather than presented as a request being met.

**jiuwenswarm PR #3610 — the one to watch.**
*支持Global/User/Session三层权限分离和持久化* (GitCode !5191, +603/−58, OPEN and
CONFLICTING at the time of writing) adds `permissions_layers.py` and
`permission_compose.py` to the directory this design targets, **rewrites
`interrupt_helpers.py`** — the closure §8.3 discusses — and injects
`compose_host_effective_permissions(global, user, session)` at the point our
`permissions` reader needs. Its axes are not ours: its *User* is a local operator
overlay file (`~/.jiuwenswarm/config/user_permissions.yaml`), its *Session* is
`session_id`, and neither is the sender. But it claims the vocabulary, the directory and
the injection point, and it moves permission persistence out of `config.yaml`.

Its composition rule is worth adopting whatever happens: strictest of Global and User,
with Session permitted to add `allow` **only where neither outer layer tightened**. That
is D4's tighten-only discipline with a controlled exception, arrived at independently.

*If #3610 merges before this is opened*, `scopes.permissions` should become a further
layer inside `permission_compose.py` rather than a second engine beside it. *If it does
not*, this design proceeds unchanged and should cite it as prior art. Either way the
schema below is unaffected — only the wiring in §11 Step 3 changes.

**agent-core PR #792 restructures the engine underneath us.**
*权限引擎职责收敛和目录整改* (GitCode !2428, roadmap issue #866, OPEN and mergeable) moves
`tiered_policy.py` → `permission_engine/toolguard/tool_policy.py` and `file_guard.py` →
`permission_engine/fileguard/`, leaving `import *` shims. **Public names survive; private
ones do not** — `_parse_level`, which `narrowing.py` imports, would break. The scene hook
and its vocabulary are copied verbatim. Favourably, both #792 and #866 state that layered
composition and product presets belong in **jiuwenswarm, not the engine**: `scopes:` lands
in space upstream is deliberately vacating.

**Shapes to copy rather than invent.**

- **List-of-rules with a matcher** already exists twice: `permissions.rules`
  (`id`, `tools`, `pattern` with glob or `re:`, `severity`) and `file_guard.paths`
  (`path`, `match`, per-verb levels). The latter is the better-engineered one — loose
  YAML compiled at load into frozen dataclasses, with `evaluate() -> None` meaning
  *no opinion*. **Naming clash:** `file_guard.paths[].match` means the match *kind*,
  where our `match:` means the criteria. Rename one or expect confusion.
- **Decision provenance** exists as strings (`tiered_policy:rules:…`,
  `file_guard:prefix:/data/public`). §12's resolver has no incumbent to displace, but
  should emit that format rather than a new one.
- **Config write-back is round-trip safe.** `_load_yaml_round_trip` /
  `_dump_yaml_round_trip` under `update_config(mutator)` preserve unknown top-level keys
  and comments, so a hand-authored `scopes:` survives the engine rewriting `config.yaml`
  for `approval_overrides` or `file_guard`. Non-obvious, and already handled.
- **No provenance resolver exists in either repo** — both merge helpers are blind, and
  agent-core's per-entry `source` key is now explicitly ignored. §12 is greenfield.
- **No connector capability registry exists.** §7 is genuinely new; the nearest idiom is
  agent_teams' capability ceiling (`enable_hitt`, `CapabilityOverrides` with
  `bool | None = None` meaning *inherit*, enforced by set subtraction).

**Two deployment facts that constrain rollout.**

- **A new top-level key must be added to `jiuwenswarm/resources/config.yaml`.** The
  template merge rebuilds an operator's file from the template's key set, so a key absent
  there is deleted from their config on upgrade.
- **The permission rail mounts on `permissions.enabled` alone**, with no channel gate at
  mount time — so `scopes.permissions` applies to `__cron__` and `__heartbeat__` too the
  moment it is enabled. §9 assumes this; it is stated here because it is easy to miss.
  `permissions.enabled` ships `false` and is gated twice in agent-core; no PR flips it.

**One reverted attempt worth knowing.** Permission modes (Full Access / Auto / Strict)
landed `81750868` and were fully reverted `cb80cea0` a day later. That work would have
migrated `enabled: false` into a *mounted* `mode=full_access` rail — a silent switch-on
of the engine. Still on the #866 roadmap. Any design that makes the engine easier to
enable should say explicitly that it does not enable it.

---

## 11. Implementation

### Step 1 — `scopes` first-class, `delivery` + `agent`

Read `scopes` and settle them at load. Capability declarations for Slack.

Both sections land together, and the split is by §3.1's rule rather than by which
process happens to resolve them: `mode` and `prompt` are `delivery`, `model_name` is
`agent`. One conversation's answer therefore spans two sections, and what the
connector reads per conversation is one carrier rather than either section:
`SlackChannelOverride` stays the shape the three per-conversation call sites already
read, but it is a carrier and not a section, and `override_as_sections` /
`sections_as_override` are named for that. Folding both sections into `delivery`
would have been shorter and would have put `model_name` under the section that does
not own it.

Lift Slack's existing validation into the shared resolver: unknown keys, bad
trigger names, `model_name` checked against configured models, a mode list omitting
`mention`. That validation is the expensive part and it is generic in shape; the
next connector should inherit it rather than reinvent it badly. The connector keeps
exactly one check for itself, and §3.1 says why: the message-time re-validation in
`_channel_model_name`, which exists because the WebUI rewrites `models.defaults`
after the config was read.

Layer 0 keeps `allow_from` and `allowed_channel_ids` untouched.

### Step 2 — matcher

`user` as a list, `not` on identity. Works for `delivery` immediately.

**Done**, for `delivery` and for `agent` alike — both are resolved in the gateway
today (§7.1), where the sender is a field on the inbound event, so §8.4's gate did
not bind either of them. It binds a section resolved *runtime-side*, and there is
not one yet.

Two things the step turned out to need that are not in the sentence above:

- **A per-message resolution path in the connector.** Step 1 settled every
  per-conversation answer once, at config apply, into a map keyed on the
  conversation. That is the whole answer while a rule can only name a
  conversation, and it cannot hold one that names a person: there is no sender at
  config time. The settled maps stay — they are the answer for every conversation
  no rule names a sender in, and for every caller that has no sender to offer, the
  startup summary included — and a second path folds the scopes again per message
  when, and only when, some scope constrains identity.
- **A rule about which sender.** Three of the four Slack call sites pass whoever
  sent the message. The fourth resumes a paused turn and passes the turn's
  initiator: a click is not a turn (D13), and a permission prompt is routinely
  answered by someone who did not start the work.

### Step 3 — `permissions`

**Done.** `channel` and `chat` scoping work at once, folded in
`jiuwenswarm/common/scopes/permissions.py` and read by the runtime hook on every
tool call. The `user` axis still waits on §8.4 — `current_conversation()` in
`scope_permissions.py` reads only `channel` and `chat` off the runtime
ContextVars.

Composition via `strictest()`, narrowing with the primitive that already exists —
`agent_teams/security/narrowing.py`'s `narrow_permissions`. It deep-copies, applies
`strictest(base_or_default, override)`, has zero `agent_teams` coupling, and jiuwenswarm
already imports it (`agents/swarm/providers/member_rails.py`). Do not write another merge.

**One caveat, written into the code and not just here:** it is monotone over the `tools`
field *only*. An `approval_overrides` hit short-circuits to ALLOW ahead of the whole-tool
baseline, so narrowing a tool from `allow` to `ask` does **not** guarantee an ask if an
override matches first. A scope that must be enforceable has to be evaluated against the
overrides too, or the two mechanisms will disagree silently — which is the failure mode
§5.4 spent order-independence to avoid. `_prune_approval_overrides` in `permissions.py` is
that evaluation: it drops a narrowed tool from `approval_overrides` in place, which is
safe to do unconditionally because an override hit can only ever resolve to ALLOW.

### Step 4 — `people` and `roles`

Turns `not: {user: [...]}` into `not: {role: ...}`. A pure refactor of step 2's
semantics.

**Done**, and the "pure refactor" turned out to be literally true in the code as
well as in the semantics. **A role is resolved into ids at load**, on the platform
the scope names, and folded into the same `users` / `not_users` tuples the `user`
axis produces. Nothing downstream changed: the matcher, the composition, the Slack
fold and the permission rail are untouched, because after compilation there is no
such thing as a role.

Three things that buys, none of which a match-time resolution would have:

- **Specificity is settled for free.** `constrains_identity` is one boolean over
  every spelling of the axis, so `{channel, chat, role}` and `{channel, chat, user}`
  are both layer 3 and rewriting a list of ids as a role cannot silently reorder
  which scope wins per key.
- **The OR (D5) is a set union performed once** rather than a branch evaluated per
  message, and the two spellings cannot drift into meaning different things.
- **The fail-closed rules are step 2's**, unchanged, rather than a second answer
  written beside them.

What it costs is that a role must know its platform: `role: admin` with no
`channel:` cannot be resolved at all, because the same role holds different ids on
each platform its members are on. §8.1's channel-required rule therefore binds
*harder* for a role than for a raw id, not more loosely.

Two call sites had to learn to pass `people:` and `roles:` — the connector's
`load_slack_scopes` and the runtime's `runtime_scopes` — and the runtime's compile
cache had to widen its key to all three blocks, since a `roles:` edit changes which
ids a scope resolves to while leaving the `scopes:` list byte for byte unchanged.

### Parallel — identity

§8.4. Gates only the user axis on runtime-side sections.

**Not closed, and not currently binding.** `user_id=str(env.user_id or "")` is in
`agent_compat.py`, so the field crosses the wire — but the line above it in our own
tree reads *"``user_id`` is a Gateway-authenticated routing identity, not channel
metadata"*, which is §8.4's first qualification stated by the code rather than about
it. The requirement §8.4 actually sets is that the matcher read the sender from the
identity bag rather than assume `AgentRequest.user_id` is it, and no such bag crosses
the WebSocket: `RoutingKey` is imported only under `jiuwenswarm/gateway/` (§8.1). The
single-writer question is still to be settled against PR #3610.

None of that binds today — not because no section is resolved runtime-side any
more (`permissions` now is, Step 3), but because that resolution reads only
`channel` and `chat`: nobody has wired the `user` axis to an identity yet
(`current_conversation()` in `scope_permissions.py` has no third field). The gate
becomes live the moment that wiring is added, and it is `permissions`' own `user`
axis, not this parallel track, that has to answer it.

### Later — cron

§9.3.

### Step 5 — `clicks` (§8.5)

Connector-side, and after Step 4 because it needs `roles` — which now exist, so the
dependency is discharged. Read the clicker from the `block_actions` payload, build the
identity bag, match. Approvals first — they are the security-relevant half.

**It split into two halves that landed separately.** D15's starter allowance and F3
needed only the turn's initiator recorded — not on the connector's activity record,
but in its own `_turn_initiators` map, for the reason `_SlackTurnInitiator`'s
docstring gives (above). Neither reads a scope, so neither waited on Step 4, and F1
was in place already. F2 belonged to the other half — it arises only once a `clicks`
rule exists to be matched — together with the `clicks` key, its capability
declaration and its composition. That is the half Step 4 gated.

**Both halves are built.** `clicks` is a section in
`jiuwenswarm/common/scopes/schema.py`, Slack declares both gestures in its
`scope_capabilities.py`, and the click handler asks one method — which returns
"no rule" rather than "nobody", so F1 is the branch every deployment that has written
nothing takes and behaviour there is unchanged. The refinements the shape in §8.5 did
not settle are recorded there, under *Built*.

The order §8.5 asked for held: the approval path was wired first and the stop button
followed the same method. On the stop path the rule is asked *last* of three — the
starter's floor, then the allow list, then the rule — and that ordering is the whole
enforcement of D15: a rule that named nobody, or named somebody other than the
starter, is never reached on the starter's own click, so there is no configuration
that locks a person out of stopping their own work. On the approval path there are
two clauses and no floor, deliberately.

§13's Q6 is dissolved rather than answered: it asked whether `clicks` should join
`DEFERRED_SECTIONS` so that a `clicks:` block warned *"deferred"* instead of *"unknown
key"*, and a section that is read warns as neither.

**The cron gap does not gate this step.** F3 gives no floor to a turn with no recorded
initiator, and a cron turn records none: the connector's initiator is read off an
inbound Slack event, and a cron run has none. That reads like a hole this step opens,
and it is not — cron turns were never reachable by the stop path to begin with (§8.5,
third case). Step 5 therefore moves interactive Slack turns from *ungated* — today any
member of a thread cancels the running turn by posting in it — to *gated*, and leaves
cron exactly where it already is. Nothing regresses, and gating the reachable half is
worth doing while the unreachable half stays unreachable.

Stopping cron runs is a **separate feature, and an addressing problem rather than an
authorization one**: the wall is that nothing can name a `cron_{ts}_{job_id}` session
sitting on no Slack channel, which is the same wall the proactive-DM direction hits
(§8.4). It is sequenced after this step, not inside it.

Note that declaring `__cron__` permissively is not available as a shortcut. Its
entry in `jiuwenswarm/common/scopes/capabilities.py` now declares `permissions`
(§9.4) — the one section resolved generically rather than by connector code —
but nothing else: no `delivery`, no `agent`, and, until this step lands, no
`clicks`, and the comment there gives the reason: nothing resolves those for
cron yet, so declaring one of them would *"promise a resolution no code
performs."* An operator writing a `__cron__` scope naming any of those today
gets §7.2's "has no effect" warning, so there is no operator
intent to honour either.

**One gesture, two intents — which is the argument for the button.** A stop is a
gesture, and Slack's only ambient one is posting a message, which the gateway already
reads as cancel (`_should_cancel_existing_stream_before_chat_send`). "Stop, you are
doing the wrong thing" and "here is one more detail" arrive identically and are
resolved identically, in favour of the first. Other surfaces avoid this by having two
inputs: Claude Code steers on typing and cancels on Esc; the web UI queues in agent
mode and interrupts in code and team mode, with an explicit control for each. Slack
has no second input — so the stop button is not only a place to hang an authorization
check, it is **the second gesture Slack currently lacks**, and that is worth as much
as the check it carries.

## 12. Deferred

- `not` on non-identity axes (§4.4)
- **a positive `role:` matched runtime-side.** Not a deferral of this step so much
  as §8.4's gate seen from the role axis: `permissions` composes with no sender, so
  a positive role reaches nobody there and a `not: {role: …}` exempts nobody. Both
  are the fail-closed direction and both are what that path already does for
  `not: {user: …}`, so nothing regressed — but "the admins may run bash here" is not
  yet expressible in the section where it would matter most, and it becomes
  expressible the moment the sender crosses the wire rather than by any further work
  on roles.
- named chat groups — the obvious next symmetry after roles; ship identity roles
  first and see whether they are asked for
- role nesting or inheritance — flat sets stay auditable; hierarchies are where
  "who can actually do this" stops being answerable by reading. Refused explicitly
  rather than read as an unknown person, and named as deferred in the warning: an
  author who writes `everyone: [admin]` had a reason, and being told `admin` is not
  a person's name would send them looking for a spelling mistake
- intersection operators — define a role instead
- **a resolver CLI**: `jiuwenswarm config effective --channel slack --chat C0…`,
  printing the merged result with each key's provenance. Worth more than config
  locality once any cascade exists, because with layering the interesting question
  is not "what is written" but "what wins", and no file layout answers that. Nothing
  upstream does this today (§10), so it is greenfield; it should emit the existing
  decision-provenance string format rather than a new one.
- **an RPC surface and a Web UI panel.** Every comparable feature has one —
  `permissions_config_rpc.py` dispatches get/set/update/delete for tools, rules and
  approval overrides; `owner_scopes` has an editor; the per-channel Slack keys this
  design replaces shipped with TypeScript and i18n. A YAML-only `scopes:` will be asked where its
  panel is. The answer — that a matcher over identity is worth getting right in one
  place before it gets an editor — is defensible, but it should be given rather than
  discovered in review.
- **a steering input beside the Stop button**, as a second first-class entry point,
  shown when `delivery.mid_turn` is not `steer`. It finishes what the button starts:
  the button gives Slack a gesture that means only "stop", and an input gives one
  that means only "steer", leaving the channel's own message box with whatever
  `mid_turn` says it means. Two text boxes in one conversation sounds confusing until
  the labels do the work — the same trick a terminal plays with Esc against typing.
  The rendering exists (`slack_inputs.py` already builds `plain_text_input` blocks in
  messages, not modals), and authorization has a slot: `clicks.steer` beside
  `approve` and `stop`, presumably with D15's floor giving the starter the right to
  steer their own turn.

  **The blocker is that the card rewrites itself**, roughly every
  `activity_card_min_edit_seconds`. A `chat.update` replaces blocks, so text typed
  and not yet submitted is wiped, and nothing tells us somebody is mid-sentence.

  **The resolution is two messages, and the record already tracks one.**
  `_SlackActivityRecord.message_ts` is the card; a sibling `controls_ts` would hold
  the input and the button, posted once and never rewritten on the timer. That also
  buys something this design already wants: the Stop button stops depending on
  `activity_card`, so turning off a *display* setting no longer removes the only
  gesture that can stop a turn — the same coupling the initiator record was kept out
  of `_SlackActivityRecord` to avoid (§8.5).

  Four things it would have to settle: the controls message must be *settled* at turn
  end, since a dead Stop button is worse than none; a state change such as
  `stop_requested` still costs one rewrite, which is fine because the hazard is the
  *periodic* rewrite rather than any rewrite; it should be posted only when there is
  something to control, or two messages a turn is noise; and both messages share one
  channel rate-limit budget. One assumption is unverified and the shape rests on it:
  that Slack preserves a `plain_text_input`'s typed value across a `chat.update` of a
  *different* message in the same thread. Worth a probe before building.
- **history beyond the originating conversation.** Settled 2026-09-02, superseding
  the three-key sketch this entry first carried and the four keys built on
  `track/AJ-history-scope-impl`. The gate and its reasoning stand; the surface
  does not.

  **One key, four words, one axis of permissiveness.**

      agent:
        history: members        # disabled | origin | members | open
                                #                        default: disabled

  `disabled` — no history tool at all. `origin` — this conversation only, which is
  what shipped before any of this. `members` — another conversation, every one
  subject to the membership rule below. `open` — as `members`, except a public
  target skips that rule. Each value is strictly wider than the one above it.

  The narrowest word is `disabled` and not `off`, which is the word this entry
  first used. A YAML 1.1 reader resolves a bare `off` to boolean `false`, so the
  operator writes a word and the loader hands the gate a boolean; quoting it works
  and relies on the operator remembering to. `disabled` reads as itself under every
  loader, and it is the one value where getting it wrong fails open.

  This replaces `history_scope` plus `history_public`, which overlapped: the
  second was a no-op unless the first said `shared`, and a key that does nothing
  without another key's value is the one an operator gets wrong. `any` is dropped
  as never having been defined, and as contradicted by the targets-only rule.

  **The gate, unchanged.** For a request in `S` about `T`:

      members(S) ⊆ members(T)

  read as *nobody in S learns anything they could not already learn*. The asker's
  own entitlement is necessary but not sufficient, because the answer is posted
  into `S`. It subsumes the DM case rather than special-casing it: there
  `members(S) = {user, bot}`, so it reduces to *the asker and the bot are both in
  T*. Bots are counted, not excluded — an integration in `S` is a reader that may
  archive or forward. Refusals name the blocking members, so an operator can act
  on them.

  **`origin` is kept, for two reasons that are not the original one.** It grants
  nothing `members` does not: for `T = S` the subset test is trivially satisfied,
  so `members` subsumes it. The reason to keep it is that it is the only setting
  whose correctness does not depend on our own gate being right — the target
  argument is not on the tool card, so there is nothing to probe — and it is the
  cheap one, since every `members` call that names a target costs a
  `conversations.info` and two paginated `conversations.members`. Describe it as a
  capability and cost switch, not as a privacy boundary.

  **Public is asymmetric, and only targets relax.** As a *target*, a public `T` is
  safe: membership is self-serve, so the content was already reachable. As a
  *source*, a public `S` is the dangerous side — the check holds when evaluated,
  and someone may join `S` afterwards to read `T` in the scrollback. `open`
  therefore relaxes targets only, enforced by there being no value that reads the
  source's privacy rather than by reading it and deciding.

  **One axis, and no others.** `history` may appear only in rules matching on
  `channel`. `not` is admissible there, because on `channel` it negates a
  platform rather than a person.

  - `user` and `role` are barred because the asker is *already* handled, and
    dynamically: the subset rule is the correct treatment of who is asking. A
    second, static treatment on the same axis is redundant, and it can grant
    exactly what membership was withholding. Barring them also keeps `not` safe
    here: negation on an *identity* axis fails open, since an unresolvable role
    matches everyone and hands them the grant.
  - `chat` was argued for and does not earn its place. The argument was that
    without it the switch reaches every DM, where the subset rule takes its most
    permissive form — which is true about the *number* of eligible targets and
    wrong about the risk. A DM source discloses to one person whom the rule has
    just established is a member of the target; they could open it and read it
    themselves. A DM is in fact the *safest* source, because its membership
    cannot grow, and growth is the one hole the rule has: the subset holds when
    evaluated, and somebody added afterwards reads the answer in the scrollback.
    That hazard belongs to channels, not DMs — the reverse of the original
    argument. What remained for `chat` was rollout and API budget, neither of
    which is a reason to put an authorization key on a second axis.

  So the feature is enabled per platform, and the membership rule is the whole of
  the protection on the source side. That is the intended shape: a static
  per-conversation list would be a second, weaker statement of what the rule
  already decides correctly and per request.

  `+`/`-` mutation is *not* offered on the list keys below: set mutation makes a
  grant unreadable, and it is what made `[-C0BSECRET]` fold to the empty set.

  **Two lists, and neither belongs in a scope.**

      channels:
        slack:
          history_never_read:     []   # conversations that may never be a target
          history_exempt_members: []   # members whose presence does not block the subset test

  Flat, matching the eight `history_*` keys already there, and beside
  `history_digest_channel_ids`' successor. Both are properties of the workspace
  rather than of one conversation: if a channel must never travel, that is true
  whichever room asks, and an integration is installed workspace-wide. Writing
  either per-scope means repeating it in every rule and forgetting it in one.

  The per-scope allow-list this entry first proposed is **dropped**. It conflated
  two jobs: rollout control, which the `chat` axis now does, and target
  protection, which the subset rule cannot express because membership is not
  sensitivity — a channel everyone belongs to passes trivially and may still be
  the last thing that should be summarised elsewhere. Only the second earns a
  key, and it is global. This also dissolves the absent-versus-empty-versus-`ALL`
  ambiguity: for a deny-list, absent and `[]` both mean "nothing is denied".

  `history_exempt_members` is a list of ids and not an `exclude_bots` boolean. A
  boolean asserts something the operator does not know, silently covers every
  integration added later, and cannot be audited. The asker is added back *after*
  the exemption is applied: theirs is the one entitlement that is definitionally
  necessary, and an exemption naming other people must not carry them.

  **`history_digest_channel_ids` is retyped, not dropped.**

      channels:
        slack:
          history: disabled     # disabled | origin | members | open
                                #                        default: disabled

  registered as the layer-0 twin of `agent.history`, the way `group_chat_mode` is
  for `delivery.mode` — which also shows the twin need not share a type. That
  gives one vocabulary, the existing two-homes warning, and a home an operator can
  edit to effect. The migration is mechanical:

      history_digest_channel_ids: []            ->  history: disabled
      history_digest_channel_ids: ["*"]         ->  history: origin
      history_digest_channel_ids: ["C0A","C0B"] ->  history: disabled, plus one
                                                    rule per chat with history: origin

  Dropping the key outright is the option to avoid: a key removed from the shipped
  template is deleted from the operator's file on upgrade, so a deployment with
  channels configured would lose history with no error and nothing in the diff.
  Use the retirement machinery that carried the connector's own per-channel keys.

  **`slack_history_digest_allowed` goes with it.** Its whole content is
  `"*" in entries or channel in entries`, and the resolved word answers the same
  question and more — `disabled` *is* `allowed=False`. It has one reader, the tool-
  registration gate, which can read the word instead. What survives is the
  mechanism, not the value: the runtime must not read connector config, so the
  connector resolves and stamps; the inbound and cron paths must reach the same
  answer for one conversation; and the answer must be taken per run rather than
  stored per job, so narrowing config narrows cron on its next firing.

  Collapsing it also removes a gate in series — today a request must satisfy the
  legacy allow-list *and* the scope key, with the legacy one winning by
  construction, because if it refuses the metadata never arrives.

  **Cron gates on membership, like anything else.** An earlier revision of this
  entry had cron refuse, on the grounds that it has a conversation but no asker,
  and that gating the room half without the sender half would protect an
  unattended repeating run more weakly than a live message. That reasoning is
  withdrawn. The asker term is belt-and-braces — the asker is normally already in
  `members(S)`, so dropping it changes nothing in the ordinary case — and the
  guarantee the rule makes is about the *audience*, which is fully checkable for
  a cron run. Who scheduled the job, and whether they are still here, does not
  bear on whether the disclosure is sound.

  For a cron run, `S` is its **delivery conversation**, and where a job delivers
  to more than one, the union of their members: a member of any delivery
  conversation who is not in `T` refuses the whole request. The gate is then
  `(members(S) - exempt) ⊆ members(T)` with no asker term, everything else
  unchanged. A DM delivery target contributes `{user, bot}` to the union exactly
  as a DM source does. A run with no delivery conversation at all refuses — the
  absence of a room is not the same as an empty one.

  The policy word is resolved per run rather than stored on the job, so narrowing
  config narrows cron on its next firing. Two costs to keep in view: a frequent
  job will miss the short-TTL membership cache and re-fetch, and the TTL must not
  be lengthened to hide that, because it is the input to a refusal and a stale
  copy is wrong for exactly that long.

  **What this asks of `track/AJ-history-scope-impl`.** The gate, the cache, the
  cron decision, the refusal vocabulary and the fail-closed branches all stand.
  What changes: four keys become one; `history_public` disappears into `open`;
  the per-scope channel list moves to layer 0 as a deny-list; `history_scope:
  current` becomes `history: origin`; the axis restriction needs enforcing in the
  capability declaration; and the branch must stop building on
  `slack_history_digest_allowed` and replace it.

  Unsettled, and deliberately not anticipated: Slack Connect and multi-channel
  guests make "member" less binary than the rule assumes. **Cross-channel history
  — a Slack request about a WeChat conversation — is a future question and must
  not shape this one.** Nothing can read another platform's conversation today, so
  it is greenfield rather than a gap; and the hard part is not scopes but that the
  subset rule would need members from two platforms, where "the same human" has no
  runtime answer here. In particular: do not add a platform dimension to these
  keys in anticipation of it.

- **`slack_search` is a second tool, not a second backend.** Slack's Real-Time
  Search API (`assistant.search.context`) offloads the matching to Slack. It is
  tempting to read that as a better implementation of the history toolkit above;
  it is not, and the two must not collapse into one tool with a switch.

  **They answer different shapes of question.** `slack_history` is exhaustive,
  ordered, and ours to process — *give me the record*. A search API is ranked,
  lossy, and Slack's judgement of what is relevant — *find what matters*.
  Summarising a thread needs the first at any price tier; "where did we discuss
  X" wants the second. Two tools, each described by what it is *for*; no
  preference order between them, which would only teach a model to reach for
  search on a summary.

  **Neither is the other's fallback, and cron settles it.** The token below
  arrives with an inbound Slack event. A cron run has none — it synthesises its
  metadata (`slack_history_metadata_for_cron_job`, §9) — so `assistant.search` is
  structurally unavailable to *every* scheduled job, and those are exactly the
  runs that read history today. History is the only path for a whole class of
  turns, not a degraded mode of search.

  **The availability gate has a per-request term.** History is decidable at
  install time (bot scopes) plus the existing per-request metadata check. Search
  stacks three more, one of which is not knowable at startup:

      search:read.public       install     granted
      is_ai_search_enabled     workspace   true (probed)
      plan tier                billing     std (probed)
      action_token             per event   unknown

  So `slack_search` cannot be a registration-time decision. It rides the same
  per-request rail history already uses, with one more term in the predicate.

  **And that term is narrower than "the turn came from an event".** Slack puts
  the condition on the event, not the turn: `message.channels` carries an
  `action_token` only when the app was @mentioned, `app_mention` carries one by
  definition, and for a DM "the @ mention is not needed and you will receive an
  `action_token` either way". So the per-event row above reads "started by a
  mention, or is a DM" — every other wake arrives with none. A turn woken by a
  bare link, by an attached file, or by `group_chat_mode: reply`/`all` has no
  token and therefore no search tool, while `slack_history` is untouched by any
  of it. "Available in Slack channels" is really "available for mentions and
  DMs", and our own channels run on `[+url]` and `[mention, url]`, which makes
  that the ordinary case rather than an edge one.

  **The authorization tension — answered 2026-09-02, and neither of the two ways
  out was right.** The tension was real: `assistant.search` matches server-side,
  so we never see the candidate set and cannot apply `members(S) ⊆ members(T)`
  before the fact. Two ways out were proposed — filter returned results by
  membership afterwards, or restrict the tool to public targets — and the second
  shipped first.

  It should not have. Slack already scopes the search by **invocation context**,
  server-side and per its documentation: called from a public channel it returns
  only public results *"regardless of whether or not the user has more granular
  scopes"*; from a private channel or MPDM, that conversation plus public
  channels; from a Slack Connect channel, only that channel. That is the audience
  rule, enforced upstream of anything we can write.

  So the public-only machinery added no safety that was not already there, and it
  removed capability: a search made from a DM could not return that DM, because
  the outbound `D`/`G` prefix filter dropped it before the caller — the very
  conversation it came from — saw it. It is removed, along with every claim in
  the card that private conversations are never returned. No membership rule of
  ours replaces it: search reads no conversation's record and has nothing for
  such a gate to be about.

  An operator toggle per tool is wanted either way, and any such key ships in the
  config template in the same change — a key honoured but not shipped is deleted
  from the operator's file on upgrade.

  **Results are references, never content — decided 2026-09-02.** Slack's terms
  for this API say *"You must not store or copy any of the data retrieved from
  this API."* A tool result here is stored twice and verbatim: in the session
  transcript, whose gate is `et.startswith("chat.")` and which inspects no tool
  name; and in the checkpoint database, as pickled agent state carrying the tool
  call and its result, written by openjiuwen rather than by this repo. The second
  *is* the model's context, so anything the model sees is on disk by
  construction, and the one insertion point for a write-path filter
  (`append_history_record`) covers the first sink and silently misses the second.
  There is no retention anywhere — no TTL, rotation or cap — and
  `SensitiveDataFilter` is a `logging.Filter` that never touches persisted
  history; neither is mitigation.

  The only lever is what the tool emits, because it changes what the model sees
  rather than where the result is written. So the tool returns what identifies
  and locates a result and never what quotes it: the model follows a `permalink`,
  or reads that conversation with the `chat_id` and `ts`. That composes the two
  tools the way they were always meant to compose. Per type: messages and files
  lose `content`; a user loses `email`, which Slack returns unrequested and which
  is a different exposure from a persisted line of chat; a channel keeps `topic`
  and `purpose`, which are the channel's description of itself rather than
  anything said in it, and without which the type answers nothing.

  Honestly stated: a strict reading of the clause forbids persisting a permalink
  too. It sits beside *"may not use any of this data for training"* and *"may not
  scrape data unrelated to user queries"*, so the evident intent is content
  retention and reuse. References are a proportionate reading, not compliance by
  construction.

  **Measured 2026-09-02, replacing what was unsettled here.** The method returns
  `ok`. `action_token` is genuinely required for a bot token — omitting it and
  sending it empty both give `invalid_action_token`, despite the reference table
  marking it Optional; the overview page's *"All API calls made using a bot token
  require an `action_token`"* is the operative statement, so per-turn availability
  is correct as built. The token now carries `search:read.public`, `.files`,
  `.im`, `.mpim`, `.private` and `.users`, and all four content types return real
  records. The top level is `{ok, results, response_metadata}` with `results` a
  dict keyed by content type, all four keys always present, and
  `response_metadata.next_cursor` paging.

  Still unsettled: the token's lifetime is undocumented, which matters because a
  long turn can reach the tool after it expires. That refusal is classified and
  reported as a fact about the turn rather than retried.

## 13. Open questions

- **Q5 — answered 2026-08-31, promoted to D15 (§8.5).** Yes: whoever started a turn
  may stop it, as an invariant floor that `clicks.stop` narrows *around* rather than a
  grant it confers. Left here as a pointer, because Q5 is cited by number elsewhere.

- **Q1** — does `delivery` want a `mode: []` idiom for "ignore entirely", or is
  that better expressed as a separate key? `[]` is terse but easy to write by
  accident.
- **Q2** — should a scope be able to name several platforms
  (`channel: [slack, feishu]`)? Consistent with `user` accepting a list, but it
  interacts with capability validation: what does an axis mean when two channels
  declare it differently?
- **Q3 — answered 2026-09-02 in §12's history entry.** Not where this question
  supposed. It is a list of conversations today, and the reading offered here was
  that it becomes a `delivery` key on scopes matching those conversations. That
  reading is rejected: what the list actually encodes is *whether history may be
  read at all*, which is one word rather than a set, and the conversations in it
  are the rollout, not the policy. It is retyped in place as
  `channels.slack.history`, the layer-0 twin of `agent.history`, taking the same
  four words; a deployment that named individual conversations expresses that as
  one scope rule per chat. Retyped rather than dropped, because a key removed from
  the shipped template is deleted from the operator's file on upgrade.
- **Q4** — is `attended` per channel, or could a channel be attended for some
  conversations and not others? A DM is attended; a broadcast channel at 3am
  arguably is not. Per channel is proposed; per scope is conceivable.
- **Q6 — dissolved 2026-09-01 by the section shipping.** It asked whether `clicks`
  should join `DEFERRED_SECTIONS` ahead of the rest of Step 5, so that a `clicks:`
  block warned *"deferred"* instead of *"unknown key"*. The question turned on whether
  anyone was expected to write `clicks:` before Step 5 landed, and Step 5 landed: the
  section is in `SUPPORTED_SECTIONS`, it is read, and it warns as neither. Left here
  as a pointer, because Q6 is cited by number in §11.

  Two things it leaves behind. `DEFERRED_SECTIONS` is empty again and is kept as a
  name rather than deleted, for the reason its comment gives — a section added ahead
  of its reader needs somewhere to be declared inert instead of being silently obeyed
  in part. And the gap it noticed is real and unclosed: §7.2's warning classes still
  have no way to say *"not built"* as against *"not a thing"*, so the next section
  written ahead of its reader will meet the same question. It is cheap to answer when
  there is one, and inventing a class for a hypothetical would be worse.

- **Q7 — answered 2026-09-01, promoted to D17 (§3.4).** No: the section stays `agent`.
  The name collides with three other senses in `config.yaml`, but it is the only one
  under which all three of the section's keys read correctly — `model_name`,
  the `system_prompt` §3.2 reserves, and a future `skills`. Left here as a pointer.
