# The web settings panel drops channel config it does not know about

Investigation only. No fix applied. Base: `local/deployed` = `1a74ee462`.

"The web UI" throughout means **jiuwenswarm's own web settings panel** — the
Channels page this project serves — **not** anything belonging to Slack.

Prior art: an earlier connector design (commits `bc21bec92`, `e8b8ce56d`)
already records the call chain and three candidate fixes. This document does not
repeat that. It answers the question that document left open — **is the fixed
field list deliberate or accidental** — and adds the measured blast radius, the
trigger condition, and the regression test.

---

## 1. Verdict: accidental. Not an allowlist.

The "deliberate allowlist" reading is refuted by five independent pieces of
evidence, three of them read directly from code or commit messages rather than
inferred.

**(a) The backend applies no filtering, and a comment in the tree says so.**
`_channel_slack_set_conf` (`jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py:5537-5568`)
validates exactly one thing — `isinstance(params, dict)` — and then passes
`params` unchanged to `cm.set_conf("slack", params)`. Any WebSocket client may
set any key. A frontend allowlist guarding a backend that accepts arbitrary
keys would be a guard on the honest path only.

This is not merely my reading. The connector carries an unknown-key warning
helper that inspects part of `channels.slack`, and its docstring
(`.../im_platforms/slack/slack_connect.py:477-479`) states it as settled fact:

> the rest of `channels.slack` is also written by a web handler that
> **persists arbitrary keys**, so warning about those would report noise no
> operator typed.

Someone working in this codebase already characterised the write path as
accepting arbitrary keys, and reasoned from it. (Read from code.)

**(b) The list was born without rationale and grew only by accretion.**
`buildSlackPayload` arrived in `c73eab2fd` (2026-07-25, `[mirror] …#1307: feat:
add Slack channel support`) as a bare object literal with 8 fields, no comment,
inside a bulk feature-mirror commit. It has since grown in exactly three
commits, each appending whatever key its own feature needed:

| SHA | Date | Subject | Field(s) added |
|---|---|---|---|
| `c73eab2fd` | 2026-07-25 | `[mirror] …#1307: feat: add Slack channel support` | initial 8 |
| `4669a28c7` | 2026-07-25 | `feat(slack): add opt-in channel automations and cron delivery` | two channel-automation keys, `acknowledge_requests`, `acknowledgement_text` |
| `389994114` | 2026-07-31 | `feat(slack): add current-channel history digests` | `history_digest_channel_ids` |
| `b60a98773` | 2026-08-04 | `feat(slack): acknowledge requests with a reaction by default` | `acknowledge_mode` (rename), `acknowledgement_emoji`, `rejected_emoji` |

None of the four commit messages mentions the list, its completeness, or a rule
for what belongs in it. `b60a98773` in particular carries a long message about
ack modes and dedup ordering while editing the list, and says nothing about it.
A deliberate security boundary does not get amended four times in silence.
(Read from history.)

**(c) Two keys were added server-side by commits that never touched the
frontend.** `612f13d8b` (2026-08-04, `feat(slack): add group_chat_mode for
channel messages`) and `ad1085318` (2026-08-12, introducing a per-channel prompt
key) each modified
`app_gateway.py`, `slack_connect.py`, all three `resources/config*.yaml`
templates, docs and tests — and **no frontend file**. Textbook drift: the schema
moved, the hand-maintained list did not. (Read from history, `git show --stat`.)

**(d) No comment, commit, or issue anywhere describes it as an allowlist.**
`buildSlackPayload` has no comment at all. A repo-wide history search for
allowlist/whitelist language returns only unrelated subsystems. The only
deliberate statement about this list found anywhere in the repo classifies it as
"a bug that exists today". (Read from history.)

**(e) The cross-connector pattern is inconsistent in exactly the way drift
predicts.** See §2 — several panels are currently *complete*, and the ones that
are incomplete are incomplete by wildly different amounts. A deliberate policy
of constraining what the UI may write would not happen to be 100% permissive for
four connectors and 58% for Slack.

**Counter-evidence, stated fairly.** Every connector panel uses the same
fixed-literal shape, which is a genuine house pattern. But it is the pattern of
*"typed draft object ↔ typed config object"* — each `build<X>Payload` mirrors a
`draftFrom<X>Config` and a `normalize<X>Config`, three hand-maintained mirrors of
one schema, driven by the TypeScript types. That is an artefact of typing the
draft, not a security decision. (Inferred, but the (a)–(d) evidence is direct.)

---

## 2. Blast radius

The in-memory mechanism is universal: `set_conf` (`channel_manager.py:237-249`)
does `merged[channel_id] = dict(new_conf or {})` — wholesale replacement — for
every connector, then fires the rebuild. Seven panels route through it with raw
`params` (`app_web_handlers.py:5349, 5400, 5456, 5507, 5558, 5609, 5671`).

**But there are two different fates for a dropped key, and the second is worse
than the defect this investigation started from.**

- **Runtime-only divergence** (telegram, dingtalk, discord, slack, whatsapp,
  wecom, wechat): the disk write goes through `update_channel_in_config`
  (`common/config.py:396-407`), key-by-key, deleting nothing. The setting stops
  applying and **resurrects on the next restart**.
- **Permanent disk deletion** (feishu, xiaoyi): the disk write goes through
  `replace_channel_subsection_with_cleanup`
  (`common/config.py:501-526`), called at `app_web_handlers.py:5218` and `:5299`
  with `keep_keys={"apps", "send_file_allowed"}`. Its final loop is
  `for k in list(section.keys()): if k not in keep_keys: del section[k]` —
  **every other key under `channels.feishu` / `channels.xiaoyi` is deleted from
  the file.** There is no restart that brings these back.

| Connector | Payload keys | Backend-read keys omitted | Fate |
|---|---|---|---|
| **xiaoyi** | 6 | `mode`, `ws_url1`, `ws_url2`, `uid`, `api_key`, `push_id`, `push_url`, `file_upload_url`, `app_id`, `phone_tools_enabled` | **deleted from disk** |
| **slack** | 14 | `group_chat_mode`, a per-channel prompt key, `enable_streaming`, `blockkit_tables`, `group_digital_avatar`, `my_user_id`, `principal_name`, `bot_name`, `enable_memory` (9 of 23 schema fields) + inert `send_file_allowed` | runtime only |
| **wecom** | 9 | `ws_url`, `enable_streaming`, `send_thinking_message`, `message_merge_window_ms`, `send_file_allowed` | runtime only |
| **feishu** | 12 | top-level keys other than `apps`/`send_file_allowed`, incl. `default_session_id`/`default_mode` (`message_handler.py:663-667`) | **deleted from disk** |
| **dingtalk** | 4 | `api_base`, `oapi_base`, `send_file_allowed` | runtime only |
| **whatsapp** | 8 | `bridge_env` (`app_gateway.py:2594`) | runtime only |
| telegram | 5 | *(none — complete)* | — |
| discord | 7 | *(none — complete)* | — |
| wechat | 13 | *(none — complete)* | — |

That telegram, discord and wechat are currently **exactly** complete, while
Slack is at 14 of 23, is itself strong support for §1's verdict. A deliberate
policy would not be 100% permissive for three connectors and 61% for one.

### 2.1 Slack (the reported case)

All nine live dropped keys are read by `app_gateway.py:2509-2551` when
rebuilding, so each reverts to its code default.
`send_file_allowed` is inert for Slack — no Slack code path reads it; it is a
template key copied from dingtalk/wecom.

Most consequential: the per-channel prompt key → `{}` (load-bearing for this
operator at the time), and `group_chat_mode` → `mention`. Slack's modes are
cumulative (`slack_connect.py:763-768`), so an operator running `all` is
silently reset to mentions-only and the bot stops reading channel traffic — and
because `group_digital_avatar` is dropped on the same save, the avatar pipeline
unregisters at `app_gateway.py:2556-2570` in the same breath.

### 2.2 xiaoyi is the most severe case, and it is not Slack

`buildXiaoyiPayload` (`ChannelsPanel/index.tsx:555-564`) sends six keys and
**never sends `app_id`**. `_merge_apps_by_id` (`app_web_handlers.py:1180-1218`)
exists precisely to preserve unsent fields, but it keys on `app_id` and
short-circuits when none is present:

```python
existing_by_app_id = {a["app_id"]: a for a in existing_apps if isinstance(a, dict) and a.get("app_id")}
if not existing_by_app_id:
    return new_apps
```

The shipped template has `xiaoyi.apps[0].app_id: null`, and `app_id` is not a
panel field, so the map is empty and **the merge is a no-op**.
`_XIAOYI_APP_DEFAULTS` (`app_web_handlers.py:1274-1292`) then fills the unsent
fields with `""`, and the cleanup writes that to disk. `push_id` is *runtime
state* written by `update_xiaoyi_runtime_in_config` (`common/config.py:418+`) —
**one panel save destroys it permanently.**

Feishu escapes this only by accident: its apps carry a real operator-entered
`app_id`, so the same merge works once configured. Its top-level keys are still
deleted.

### 2.3 Related defects found in passing

- **wecom `default_chat_id`.** `buildWecomPayload` writes it and
  `wecom_connect.py:1033` reads it (heartbeat/scheduled-push target), but the
  template does **not** ship it — so `_deep_merge` deletes it from disk on the
  next config upgrade. `last_chat_id` (written at runtime,
  `wecom_connect.py:895`) is in the same position. This is §5's instance (1)
  biting today, independent of any panel save.
- **wecom `send_thinking_message`** defaults to `True` in both the model
  (`wecom_connect.py:50`) and the loader (`app_gateway.py:2643`) while the
  template ships `false`. Dropping it therefore **turns thinking messages on** —
  a visible behaviour change, not a silent no-op.
- **dingtalk `api_base`/`oapi_base`** fall back to the public domains
  (`app_gateway.py:92-93`), so a private-cloud or international deployment
  silently loses its endpoint override until restart.
- **xiaoyi `phone_tools_enabled`** is read at *top level* (`interface_deep.py:5246`
  and two other sites) while the template ships it under `apps[]` — and the
  top-level copy is exactly what the cleanup deletes.

---

## 3. Opening the panel is safe. Only saving triggers it.

**Telling the operator not to open the panel is overcautious.** Verified:

- `channel.slack.set_conf` is called from exactly one place in the frontend,
  `handleSaveSlackConfig` (`ChannelsPanel/index.tsx:1836`) — no other caller.
- That handler returns immediately unless `hasSlackConfigChanges`
  (`index.tsx:1831`), and the Save button is `disabled` on the same condition
  (`index.tsx:3129`).
- `hasSlackConfigChanges` (`index.tsx:1412-1433`) compares only the same 14
  fields. Nothing outside those 14 can make it true.
- Opening the panel calls `fetchSlackConfig()`, a pure read.

So the sequence required is: open the Slack section → **edit one of the 14
managed fields** → click Save. Viewing, refreshing, and Cancel are all safe.
The accurate warning is *"do not save the Slack section"*, not *"do not open the
panel"*.

One sharp edge worth knowing: because `hasSlackConfigChanges` ignores the other
nine keys, the panel cannot even *show* a change to them, so an operator has no
in-UI cue that those keys exist or are at risk.

---

## 4. Nothing detects it, and it heals on restart

Confirmed, and it is the worst combination.

After a save: in-memory `channels.slack` = 14 keys; on disk = 24, because
`update_channel_in_config` (`common/config.py:396-407`) assigns key-by-key and
deletes nothing. The live connector is rebuilt from the 14. On the next restart
the gateway reads the 24-key file and behaviour silently returns. **The operator
sees a correct config file and wrong behaviour, with no error, no log line, and
a symptom that vanishes if they restart to investigate.**

The one mechanism that could have caught it does not. The unknown-key warning
helper (`slack_connect.py:457`) runs on exactly this path
(`app_gateway.py:2505`, inside the rebuild), but it only reports keys that are in
the part of the block it inspects and are *unrecognised*. A key that has been
**removed** is not unrecognised — it is absent. The function inspects the
already-truncated block and correctly finds nothing wrong with it.

---

## 5. The same failure mode occurs three times, and they are partly aware of each other

The brief framed this as three instances. Counting properly, there are **five
hand-maintained lists of known config keys plus one unenumerable read path**,
and anything absent from any of them is dropped silently:

1. **`_deep_merge`** (`common/config.py:1796-1828`) iterates the *template*; a
   user key with no template counterpart is deleted from the file on upgrade.
   Documented and intended — "Remove: fields only in user (deprecated config,
   cleanup)".
2. **`build<X>Payload`** — this document. Drops from memory; heals on restart.
3. **`replace_channel_subsection_with_cleanup`** (`common/config.py:501-526`) —
   an inverted list: a `keep_keys` set of two, everything else deleted from disk.
   §2.2. This one is the most destructive and was not in the original count.
4. **The gateway constructor calls** (`app_gateway.py:2225, 2303, 2376, 2411,
   2436, 2460, 2509, 2608, 2636, 2677`) — a per-field list of
   `conf.get("…")` arguments. It is a strict *subset* of the declared schema for
   dingtalk (5 of 11) and wecom (10 of 15), so the schema is not the authority
   on what is actually read.
5. **The shipped templates** (`resources/config*.yaml` ×3), which must list every
   key or (1) deletes it.

Plus a **sixth, unenumerable** path: direct
`get_config()["channels"][name][key]` lookups scattered across the tree —
`send_file_allowed` (`runtime_tools.py:135`, `interface_deep.py:6117`),
`default_session_id`/`default_mode` for any channel
(`message_handler.py:663-667`), wecom `last_chat_id`/`default_chat_id`
(`wecom_connect.py:1033`), xiaoyi `phone_tools_enabled`, slack `bot_token`
(`slack_history.py:308-315`), cron `last_*` (`cron/scheduler.py:1494`). No
schema covers these, so **no mechanical diff can catch them** — and they are
exactly the keys instance (3) deletes outright.

And the guard written for this exact failure mode, the unknown-key warning
helper, is defeated by (1): a genuine typo in the config file is deleted by the
template merge before the connector ever sees it.

**Were they designed as a set? Partly — and this is the one finding that cuts
against the tidy story.** That helper's docstring
(`slack_connect.py:463-479`, added by `b49d50492`) cross-references *both* other
mechanisms explicitly:

> Nothing in the config layer reports an unrecognised key — **the only
> mechanism that compares a user's keys against a known set is the template
> merge, which deletes what it does not recognise without saying so** — and
> this is where the block is already in hand.

and

> the rest of `channels.slack` is also written by a **web handler that persists
> arbitrary keys**

So one author saw all three. But there is **no shared constant, no shared
helper, and no commit touching more than one of them** — the awareness was
recorded in a docstring and went no further. That is why this is worth stating
plainly: the knowledge exists in the tree and has already failed to propagate
once.

---

## 6. Is there a single source of truth? Yes — the shipped template.

This determines what any fix can achieve, so it is worth being precise.

- **Every connector has a declared schema.** Dataclass (telegram, discord,
  slack, whatsapp, xiaoyi) or pydantic `BaseModel` (feishu, dingtalk, wecom,
  wechat). None is a bare `conf.get()` scatter at the channel level.
  `SlackChannelConfig` (`slack_connect.py:742-807`) yields its 23 field names
  from `dataclasses.fields()` at runtime.
- **The template is machine-readable and, by project convention, complete.**
  `resources/config.yaml` → `channels.slack` has 24 keys — the 23 dataclass
  fields plus the inert `send_file_allowed`.
- **But the schema is not the authority on what is read.** The effective read
  set is the hand-written constructor call in `app_gateway.py`, which is a
  strict subset of the schema for dingtalk and wecom (§5 item 4). So even a
  perfect schema-to-template test would not prove a key is honoured.
- **The frontend is not introspectable from Python, and vice versa.** The list
  lives inside an object literal in a 3000-line `.tsx`. There is no codegen, no
  shared schema file, no OpenAPI/JSON-Schema artefact anywhere in the repo.
- **And the sixth read path (§5) is not enumerable at all.**

**So a single source of truth exists in principle — the template — but nothing
derives from it, and two of the six consumers could not be made to.** That is
the constraint that explains why there are so many lists. It bounds what any fix
can achieve: mechanical comparison can cover the four declared lists, and cannot
cover the scattered direct reads.

---

## 7. Recommendation

The three sketched options (widen the list / merge in the frontend / preserve
unknown keys in `set_conf`) are all write-path fixes. Given the verdict in §1 —
the list is accidental, not a safety property — **merging removes nothing worth
keeping**, and the objection that it would strip a security guarantee does not
survive `app_web_handlers.py:5537-5568`.

But none of the three prevents recurrence, and that is the actual defect. My
recommendation is therefore **two changes, sequenced**, and I would not ship the
first without the second.

### 7.1 Primary: make `set_conf` merge instead of replace

*What changes:* `channel_manager.py:237-249`, one line —
`merged[channel_id] = {**dict(self._config.get(channel_id) or {}), **(new_conf or {})}`.

*Size:* a handful of lines, Python only, **no UI rebuild** — which matters here,
because `dist/` is gitignored and a frontend fix cannot be deployed from a fresh
worktree without a build.

*What it protects against:* every connector at once, and every future key any
panel forgets. It closes the in-memory/on-disk divergence for slack, wecom,
dingtalk, feishu and xiaoyi in one change.

*What it does NOT protect against — read this part carefully:*
- **It does nothing for xiaoyi or feishu.** Their disk loss goes through
  `replace_channel_subsection_with_cleanup` (§2.2), a different function on a
  different line. The most severe case in the whole blast radius is untouched by
  the fix for the reported one. **xiaoyi should be treated as a separate,
  higher-priority bug**, not as something this fix covers.
- **It removes the ability to delete a key through this path.** Omission
  currently means "delete"; after the change it means "unchanged". Any caller
  relying on omission-to-delete breaks silently. I checked the nine call sites
  (`app_web_handlers.py:5215, 5297, 5349, 5400, 5456, 5507, 5558, 5609, 5671`)
  and none appears to depend on it, but feishu/xiaoyi send `{"apps": …}` alone
  and would need re-reading before this lands.
- **It does not fix `_deep_merge`.** After this change the operator is protected
  in memory and still not on disk — a config upgrade will still delete
  wecom's `default_chat_id` and any key missing from the template. This is
  arguably *more* confusing than today, so §5's instance (1) should be
  sequenced next, not assumed solved.
- It does not fix stale in-browser state: a panel loaded before a file edit
  still posts the old values for the 14 fields it does manage.
- It does not make the missing keys *editable* — nine Slack settings remain
  file-only.

**Sequencing implied by the above:** (i) xiaoyi disk deletion, (ii) this
`set_conf` merge, (iii) the regression test, (iv) `_deep_merge` / template
completeness. Fixing only (ii) leaves the worst case standing.

### 7.2 Required companion: the regression test

Without this, §7.1 fixes today's symptom and the next added key drifts again in
silence. See §8.

### 7.3 What I would not do

**Widening the field list alone** (adding the two, or ten, missing keys) is the
narrow fix the "deliberate" reading would have implied. Since the list is
*not* deliberate, this fixes today's ten keys and guarantees an eleventh. It
also needs a UI rebuild. It is worth doing eventually so the settings become
editable, but it is a feature, not this fix.

---

## 8. The regression test

**What it compares:** the key set of `channels.slack` in
`jiuwenswarm/resources/config.yaml` against the field names of
`SlackChannelConfig`, and against the keys `buildSlackPayload` returns.

**Where it lives:** `tests/unit_tests/test_resource_config.py`. That file
already loads the template and already asserts on `channels.slack`
(`test_slack_digital_avatar_ships_disabled`, `:41-60`), so the mechanism is
present and needs no new infrastructure. It runs in the Python suite, which is
the suite CI actually runs.

**Is it feasible?** Yes, in three tiers of decreasing robustness:

1. **Template ↔ dataclass** — fully robust.
   `{f.name for f in dataclasses.fields(SlackChannelConfig)}` against the
   template keys. Pure Python, no parsing. Catches a key added to the schema and
   forgotten in the template — which is instance (1) of §5, the one that deletes
   from disk. **This tier is worth adding on its own merits.** It would need to
   allow-list `send_file_allowed` as a known template-only key, or that key
   should be removed from the Slack section.

2. **Template ↔ `app_gateway.py` construction** — also pure Python: assert every
   dataclass field is passed in the `SlackChannelConfig(...)` call. Catches
   §5 instance (3).

3. **Template ↔ `buildSlackPayload`** — feasible but the weak link. A Python
   test must extract the key set from the `.tsx` by regex over the function
   body. That is brittle against reformatting, and it is the honest caveat here:
   **the frontend list is not introspectable from Python**, and there is no
   codegen or shared schema to make it so.

   The repo already has the pattern that fixes this. `buildWechatPayload` lives
   in its own module, `ChannelsPanel/wechatTypes.ts:186-202`, and is
   **exported** — precisely the extract-pure-logic-to-a-testable-module shape
   the frontend uses for its `node --test` suites (see the ~20 `test:*` scripts
   in `frontend/package.json`). Moving `buildSlackPayload` into a
   `slackTypes.ts` alongside it would make tier 3 a clean assertion instead of a
   regex, and would need a new `test:*` script.

**Recommended:** tiers 1 and 2 now — they are cheap, robust, pure Python, and
catch the two instances that damage disk state. Tier 3 as regex initially, with
the `slackTypes.ts` extraction as the follow-up that makes it sound.

All three tiers should be **parametrised over all nine connectors**, not written
for Slack alone. Slack is where the divergence was noticed; §2 shows it is not
where it is worst, and a Slack-only test would have stayed green through the
xiaoyi case.

**What the test does not catch:**
- It compares *names* only. A key present everywhere but misinterpreted, or a
  panel widget writing the wrong type, passes all three tiers.
- It cannot cover the sixth read path (§5) — scattered
  `get_config()["channels"][…]` lookups with no schema. Those keys are
  invisible to any mechanical diff, and they are precisely the ones
  `replace_channel_subsection_with_cleanup` deletes.
- It does not detect the divergence at *runtime*; it fails a build. Nothing
  proposed here tells a running operator that their config was truncated.

---

## 9. Summary for the operator

- **The fixed field list is accidental drift, not a safety allowlist.** Fix it
  by merging; nothing is lost. The backend filters nothing, and a docstring in
  the tree already says so.
- **Opening the Channels panel is safe.** Editing one of the 14 managed Slack
  fields and clicking Save is what triggers it. The standing advice can be
  relaxed from "do not open the panel" to "do not save the Slack section".
- **Ten Slack keys are affected, not two** — nine of them live, including
  `group_digital_avatar` and the operator's per-channel prompt key.
- **Slack is not the worst case.** Saving the **xiaoyi** panel deletes keys from
  `config.yaml` permanently, including the runtime `push_id`. That does not heal
  on restart and is not fixed by fixing Slack. Feishu loses its top-level keys
  the same way.
- **Nothing detects any of it** — confirmed, including that the one guard that
  might have caught it structurally cannot.
- **After the recommended fix, disk is still unprotected** — `_deep_merge` will
  still silently delete template-missing keys, and wecom's `default_chat_id` is
  being deleted that way today.
