# `blockkit_tables` and `render_tables`: nested, not redundant, and misnamed

Question raised 2026-08-27: two Slack config keys both appear to govern table
rendering. **They are not duplicates — but the names say the opposite of what
each one does, and whether they should stay separate is open.**

## What each actually does

| key | values | scope |
|---|---|---|
| `blockkit_tables` | `off` / `marker` / `auto` | whether **any** Block Kit rendering happens at all |
| `render_tables` | `off` / `basic` / `data_table` | given blocks are allowed, **which** block a Markdown table becomes |

They are evaluated in that order, in `_blocks_and_kind_for`
(`slack_connect.py:9511`):

```python
mode = self._blockkit_tables_mode()
if mode == BLOCKKIT_TABLES_OFF or requested is False:
    return None, BLOCK_KIND_UNKNOWN
if requested is not True and mode != BLOCKKIT_TABLES_AUTO:
    return None, BLOCK_KIND_UNKNOWN
rendered = slack_blocks.render_blocks_with_kind(
    text, requested=..., render_tables=self._render_tables_mode(), ...)
```

`blockkit_tables` is checked and can return **before `render_tables` is consulted
at all**. So it is an outer gate and the other is an inner choice. `marker` on
the outer gate means "render only when the reply explicitly asks", which has no
counterpart on the inner one.

## The naming is inverted

**`blockkit_tables` is the key that is not about tables.** Because it returns
before `render_blocks_with_kind` is reached, `blockkit_tables: off` suppresses
*everything* that function would have built — ` ```mermaid ` diagrams,
` ```vega-lite ` charts, hand-written ` ```blockkit ` fences — not only tables.

`render_tables` is the key that *is* table-specific: `render_tables: off` leaves
a Markdown table as pipes while a mermaid diagram beside it still renders.

So a reader reasoning from the names gets both backwards. This is not
hypothetical: the two keys were treated as a deprecated pair during a config
audit on 2026-08-27, on the strength of the shared word "tables", and only the
code settled it.

## The genuine overlap

Both have an `off`, and the two `off`s differ in scope:

- `blockkit_tables: off` — no blocks of any kind
- `render_tables: off` — no table blocks; other block kinds unaffected

Two settings whose names suggest the same subject, each with an `off` meaning
something different, is the part worth revisiting. It is a real overlap rather
than a real duplication.

## Open: should they be one key?

Not decided, and **not urgent** — nothing is broken, and both are read correctly.
Arguments each way, so that whoever picks this up does not have to re-derive
them:

**For merging.** A single ordered setting — `off` / `marker` / `basic` /
`data_table` — expresses every combination anyone would want, and removes the
question of what `blockkit_tables: auto` plus `render_tables: off` means (answer:
diagrams render, tables do not, which is reachable but which nobody would
describe that way).

**Against merging.** The outer gate governs a superset of block kinds. Folding
the table choice into it makes a key named after tables decide whether mermaid
renders, which is the same naming error in a new place. A rename may be the whole
fix: `blockkit_tables` → something naming blocks rather than tables.

**Cheapest option, if the pair stays.** Fix only the comment in the shipped
template so the outer key states its real scope. Costs nothing and removes the
trap that already caught one audit.

## If it is renamed: candidates, and two traps

`render_blockkit` was proposed, on the reasoning that the key is about Block Kit
rendering rather than about tables. That reasoning is right and the current name
should go. The specific candidate has two problems, both checkable rather than
matters of taste.

**`blockkit` already names something narrower.** `slack_blocks.py` defines
`_FENCE_LANGUAGE = "blockkit"` alongside `"mermaid"`, `"vega-lite"` and
`"slack-raw"`. So a reply can hand over a ` ```blockkit ` fence specifically, and
`render_blockkit: off` reads as "do not render those fences" when it in fact
suppresses mermaid and vega-lite too. That is the same too-narrow reading the
rename exists to fix, moved to a new word.

**There is a `blockkit_*` family, and `render_*` is not one.** The shipped
template carries four:

```
blockkit_tables               blockkit_allowed_block_types
blockkit_allow_interactive    blockkit_validate
```

against a single `render_tables`. Moving one key out of the four-key family and
into the one-key family costs the grouping that makes the other three findable.

### The three real options

| candidate | for | against |
|---|---|---|
| `render_blocks` | matches the umbrella function it gates -- `render_blocks()` / `render_blocks_with_kind()` at `slack_blocks.py:609,628` -- and no fence carries that name | still leaves the family split three-and-two |
| `blockkit_mode` | keeps the family intact, drops "tables", and `off`/`marker`/`auto` genuinely are modes | "mode" says nothing about what is being moded; needs its comment to carry the scope |
| `render_blockkit` | pairs visually with `render_tables`, making the nesting legible | collides with the fence language; splits the family |

`render_blocks` is the most accurate of the three: the key's whole job is to
decide whether `render_blocks` is called, and it is named after no narrower
thing. `blockkit_mode` is the least disruptive. Both are better than the current
name; the choice between them is a judgement about whether the family or the
accuracy matters more, and has not been made.

**Whichever is chosen, `render_tables` keeps its name** -- it is already correct.

## The values need renaming too, and one of them is worse than it looks

`marker` does **not** mean "fenced Block Kit only". `_extract_block_request`
(`slack_connect.py:9609`) reads two literal markers out of the reply text and
returns `True`, `False` or `None`; the fence languages play no part:

```python
if _SLACK_BLOCKS_OFF_MARKER in cleaned:  requested = False
if _SLACK_BLOCKS_MARKER    in cleaned:  requested = True
if requested is None:  return content, None   # only then does the mode decide
```

So `marker` means **"render everything, but only when the reply asks"** -- a
marked reply gets tables, mermaid, vega-lite and ` ```blockkit ` fences alike; an
unmarked one gets none of them. It is an opt-in gate, not a content filter.

**`marker` names a mechanism that is already proposed for removal.** There is a
standing proposal to drop the render markers and auto-render mermaid. If it
lands, a config value called `marker` names something that no longer exists.
**`explicit`** describes the policy rather than the mechanism -- "the reply has
to opt in" -- and survives that change whatever the opt-in becomes. It is the
better word today and the only one of the two that stays correct.

So: `off` / `explicit` / `auto`, and the rename costs nothing.

## Three decisions, and only two of them are free

These were tangled together when the question came up, and separating them is
most of the work:

1. **Rename the key.** `render_blocks` or `blockkit_mode`, per the table above.
   No behaviour change.
2. **Rename the middle value**, `marker` -> `explicit`. No behaviour change, and
   it outlives the marker mechanism.
3. **Re-scope the middle value** so it means "fenced Block Kit only" rather than
   "everything, on request". **This is a behaviour change, not a rename**, and
   needs its own case.

Both readings of the middle value are coherent designs -- one makes it a
content-kind filter, the other an opt-in gate -- and today's is the second. The
proposal that raised this assumed the first, which is worth deciding on its
merits rather than adopting by way of a rename. Doing 1 and 2 without 3 is safe
and can happen whenever the file is next touched.

## Before changing either

Both keys are **ours**, absent from `upstream/develop` — measured, not assumed:

```
blockkit_tables             0 files in upstream/develop
render_tables               0 files in upstream/develop
data_table_row_threshold    0 files in upstream/develop
```

So a rename needs no migration for anyone outside this deployment — see
[[retro-compat-for-unshipped-features]] for why that matters, and
[[config-template-prunes-unlisted-keys]] for the rule that any renamed key must
land in the shipped template in the same commit.
