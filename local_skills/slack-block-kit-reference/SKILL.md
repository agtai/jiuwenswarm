---
name: slack-block-kit-reference
description: 'Field-level reference for Slack Block Kit JSON — every block, block element and composition object, with required and optional fields, value limits, allowed child types, and which surfaces (messages, modals, Home tabs) each one is valid on. Use before hand-writing or editing a Block Kit payload: a `blocks` array, a modal or Home tab view, a section / actions / input / rich_text / table / card / data_visualization block, an accessory or input element, or an option, text or confirm object. Also use to check whether a block type, field name, enum value or limit is real rather than recalled. Not needed for ordinary plain-text or Markdown messages that carry no Block Kit JSON.'
---

# Slack Block Kit Reference

Block Kit is Slack's declarative UI format. A payload is a JSON array of **blocks**; blocks
contain **block elements**; blocks and elements embed **composition objects** such as text
objects and option objects. This skill is a transcription of Slack's own Block Kit reference so
that a payload can be written correctly without going to look it up.

Read the relevant reference file before writing a payload that uses anything beyond a plain
`section` with a text object. Field names, requiredness, limits and surface availability are
exactly the details that get misremembered, and Slack rejects a payload with an invalid field
rather than ignoring it.

## Formatting convention used here

Block Kit JSON in this skill's Markdown is fenced as ` ```blockkit ` rather than ` ```json `.
Use that same tag when writing Block Kit JSON into Markdown.

## What is in each file

| File | Covers | Read it when |
|---|---|---|
| `references/blocks.md` | 21 blocks — the top-level entries of a `blocks` array | Choosing or configuring a block |
| `references/block-elements.md` | 46 elements — buttons, menus, inputs, rich-text runs, mentions | Putting anything inside a block |
| `references/composition-objects.md` | 11 composition objects — text, option, option group, confirm, filter, dispatch config, Slack file, Slack icon, workflow, trigger, input parameter | Filling a field whose type is "Object" |

Each entry gives the `type` value, the surfaces it is available on, the blocks or elements it is
compatible with, a full field table (field, type, required, description with limits), usage notes,
and worked JSON examples. The files are long; jump to the entry you need rather than reading a
whole file end to end.

## Payload shape

A message payload carries its blocks in a `blocks` array:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "A message *with some bold text* and _some italicized text_."
      }
    },
    {
      "type": "divider"
    }
  ]
}
```

- Up to **50 blocks** in a message; up to **100 blocks** in a modal or Home tab.
- Every block needs `type`. `block_id` is optional and generated if omitted; maximum 255
  characters, and it should be unique per message and per iteration of a message — when a message
  is updated, use a new `block_id`.
- Every interactive element needs `action_id`, unique among the elements of its containing block;
  maximum 255 characters.

## Surface compatibility

The three surfaces are **messages**, **modals** and **Home tabs**. A block or element that is not
available on the surface being targeted is an error, not a graceful degradation. This matrix is
the fastest thing to check before writing anything.

### Blocks

| Block | `type` | Messages | Modals | Home tabs |
|---|---|---|---|---|
| Actions | `actions` | yes | yes | yes |
| Alert | `alert` | -- | yes | -- |
| Card | `card` | yes | yes | yes |
| Carousel | `carousel` | yes | -- | yes |
| Container | `container` | yes | -- | yes |
| Context | `context` | yes | yes | yes |
| Context actions | `context_actions` | yes | -- | -- |
| Data table | `data_table` | yes | -- | yes |
| Data visualization | `data_visualization` | yes | -- | -- |
| Divider | `divider` | yes | yes | yes |
| File | `file` | yes | -- | -- |
| Header | `header` | yes | yes | yes |
| Image | `image` | yes | yes | yes |
| Input | `input` | yes | yes | yes |
| Markdown | `markdown` | yes | -- | -- |
| Plan | `plan` | yes | -- | -- |
| Rich text | `rich_text` | yes | yes | yes |
| Section | `section` | yes | yes | yes |
| Table | `table` | yes | -- | yes |
| Task card | `task_card` | yes | -- | -- |
| Video | `video` | yes | yes | yes |

### Elements

The last column is the constraint most often got wrong: an element may only appear inside the
blocks named there.

| Element | `type` | Messages | Modals | Home tabs | Allowed in blocks |
|---|---|---|---|---|---|
| Attachment mention | `attachment_mention` | yes | yes | yes | Rich text |
| Broadcast | `broadcast` | yes | yes | yes | Rich text |
| Button | `button` | yes | yes | yes | Section, Actions |
| Canvas | `canvas` | yes | yes | yes | Rich text |
| Canvas message unfurl | `canvas_message_unfurl` | yes | yes | yes | Rich text |
| Canvas user mention | `canvas_user_mention` | yes | yes | yes | Rich text |
| Channel | `channel` | yes | yes | yes | Rich text |
| Checkboxes | `checkboxes` | yes | yes | yes | Section, Actions, Input |
| Citation | `citation` | yes | yes | yes | Rich text |
| Color | `color` | yes | yes | yes | Rich text |
| Date | `date` | yes | yes | yes | Rich text |
| Date picker | `datepicker` | yes | yes | yes | Section, Actions, Input |
| Datetime picker | `datetimepicker` | yes | yes | -- | Actions, Input |
| Email input | `email_text_input` | -- | yes | -- | Input |
| Emoji | `emoji` | yes | yes | yes | Rich text |
| Feedback buttons | `feedback_buttons` | yes | -- | -- | Context actions |
| File | `file` | yes | yes | yes | Rich text |
| File input | `file_input` | -- | yes | -- | Input |
| Icon button | `icon_button` | yes | -- | -- | Context actions |
| Image | `image` | yes | yes | yes | Section, Context |
| Link | `link` | yes | yes | yes | Rich text |
| List record | `list_record` | yes | yes | yes | Rich text |
| Message mention | `message_mention` | yes | yes | yes | Rich text |
| Multi-select menu | `multi_static_select` / `multi_external_select` / `multi_users_select` / `multi_conversations_select` / `multi_channels_select` | yes | yes | yes | Section, Actions, Input |
| Number input | `number_input` | -- | yes | -- | Input |
| Overflow menu | `overflow` | yes | yes | yes | Section, Actions |
| Plain-text input | `plain_text_input` | yes | yes | yes | Input |
| Radio button group | `radio_buttons` | yes | yes | yes | Section, Actions, Input |
| Rich text input | `rich_text_input` | -- | yes | yes | Input, Table |
| Rich text list | `rich_text_list` | yes | yes | yes | Rich text |
| Rich text preformatted | `rich_text_preformatted` | yes | yes | yes | Rich text |
| Rich text quote | `rich_text_quote` | yes | yes | yes | Rich text |
| Rich text section | `rich_text_section` | yes | yes | yes | Rich text |
| Salesforce data field | `salesforce_data_field` | yes | yes | yes | Rich text |
| Select menu | `static_select` / `external_select` / `users_select` / `conversations_select` / `channels_select` | yes | yes | yes | Section, Actions, Input |
| Tag | `tag` | yes | yes | yes | Rich text |
| Team | `team` | yes | yes | yes | Rich text |
| Text | `text` | yes | yes | yes | Rich text |
| Time picker | `timepicker` | yes | yes | yes | Section, Actions, Input |
| URL input | `url_text_input` | -- | yes | -- | Input |
| URL source | `url` | yes | -- | -- | Task card |
| User | `user` | yes | yes | yes | Rich text |
| Usergroup | `usergroup` | yes | yes | yes | Rich text |
| Work object mention | `work_object_mention` | yes | yes | yes | Rich text |
| Workflow button | `workflow_button` | yes | -- | -- | Section, Actions |
| Workflow mention | `workflow_mention` | yes | yes | yes | Rich text |

Composition objects carry no surface of their own; they are valid wherever the block or element
that embeds them is valid.

## Things that are routinely got wrong

- **A text field is an object, not a string.** `section.text`, `header.text`, `button.text` and
  most others take a text object `{"type": "mrkdwn" | "plain_text", "text": "..."}`. This holds
  even where a field table says "String": the `card` block types `title`, `subtitle`, `body` and
  `subtext` as String and rejects bare strings for all four, and `container.title` and
  `container.subtitle` are typed the same way but exemplified as text objects. The genuine bare
  strings are few — `markdown.text`, `data_table` cell `text` inside a `raw_text` or `raw_number`
  cell object, `plan.title`, `task_card.title`, `data_visualization.title`, `icon_button.icon`.
  Where a field table and the block's own example disagree, the example is right.
- **The type cell is unreliable in both directions, so the card block's rule does not generalise.**
  `card.title` is typed String and must be a text object; `plan.title` is typed Object and must be
  a **bare string**, refusing a text object with
  `invalid_blocks: must provide a string`. Two neighbouring blocks contradict their own
  documentation in opposite directions. Having learned one of them, do not carry it to the other:
  look each field up.
- **`rich_text` does not parse emoji shortcodes.** `":white_check_mark:"` inside a `text` element
  renders as literal colons and letters. Use a sibling `{"type": "emoji", "name":
  "white_check_mark"}` element instead. The trap is that `mrkdwn` in a `section` *does* parse the
  same shortcode, so moving a string between the two silently changes what it renders, with no
  error to notice. Literal unicode emoji do render in `text`, but the element form is preferred:
  it names the emoji rather than carrying a code point, and does not depend on source encoding.
- **`mrkdwn` is not Markdown.** Bold is `*single asterisks*`, italic is `_underscores_`, links are
  `<https://example.com|label>`, strikethrough is `~tildes~`. The `markdown` block is the one
  place that takes standard Markdown instead, and it is messages-only.
- **`plain_text` only, in many places.** Header text, input labels and hints, select placeholders,
  and confirmation dialog title/text/confirm/deny must all be `plain_text`; passing `mrkdwn` there
  is rejected.
- **`slack_icon` is the field name, not the object's type.** The card block's `slack_icon` takes
  `{"type": "icon", "name": "sparkle"}`. `type` is the literal string `icon`; the icon is chosen by
  `name`, never by a field called `icon`; and `name` must be one of exactly 54 values listed in
  `references/composition-objects.md`. The values are a closed set with no derivable pattern —
  `sparkle` is singular, for instance — and an undocumented one rejects the whole message.
- **Elements are not interchangeable between blocks.** `section` takes exactly one element in
  `accessory`; `actions` takes an `elements` array of up to 25; `context` takes up to 10 image
  elements and text objects; `input` takes exactly one element in `element`. The rich-text
  elements only ever appear inside a `rich_text` block, nested in a `rich_text_section`,
  `rich_text_list`, `rich_text_quote` or `rich_text_preformatted`.
- **Options carry `text` and `value`, both required.** `value` is what comes back in the
  interaction payload; maximum 150 characters. Option `text` is capped at 75 characters.
- **Limits are enforced.** Section `text` 3000 characters; section `fields` at most 10 items of
  2000 characters each; header `text` 150; input `label` and `hint` 2000 each; `markdown` blocks
  12,000 characters cumulative per payload; `table` 100 rows of at most 20 cells and 10,000
  characters per message; at most 2 `data_visualization` blocks per message.
- **Interactivity needs handling.** Any block with an interactive element produces an interaction
  payload when used, keyed by `block_id` and `action_id`. An element with a `url` still produces
  one and still needs acknowledging.

## Worked examples

A section with an accessory element:

```blockkit
{
  "type": "section",
  "text": {
    "type": "mrkdwn",
    "text": "*Haley* has requested you set a deadline for finding a house"
  },
  "accessory": {
    "type": "datepicker",
    "action_id": "datepicker123",
    "initial_date": "1990-04-28",
    "placeholder": {
      "type": "plain_text",
      "text": "Select a date"
    }
  }
}
```

An actions block with a select menu and a button:

```blockkit
{
  "type": "actions",
  "block_id": "actions1",
  "elements": [
    {
      "type": "static_select",
      "action_id": "select_2",
      "placeholder": {
        "type": "plain_text",
        "text": "Which witch is the witchiest witch?"
      },
      "options": [
        {
          "text": { "type": "plain_text", "text": "Matilda" },
          "value": "matilda"
        },
        {
          "text": { "type": "plain_text", "text": "Glinda" },
          "value": "glinda"
        }
      ]
    },
    {
      "type": "button",
      "action_id": "button_1",
      "text": { "type": "plain_text", "text": "Cancel" },
      "value": "cancel"
    }
  ]
}
```

An input block, for a modal or Home tab view:

```blockkit
{
  "type": "input",
  "block_id": "input123",
  "label": {
    "type": "plain_text",
    "text": "Label"
  },
  "element": {
    "type": "plain_text_input",
    "action_id": "plain_input",
    "multiline": true
  },
  "optional": false
}
```

A rich text block, showing the nesting the rich-text elements require:

```blockkit
{
  "type": "rich_text",
  "elements": [
    {
      "type": "rich_text_section",
      "elements": [
        { "type": "text", "text": "Hello there, " },
        { "type": "text", "text": "I am a bold rich text block!", "style": { "bold": true } }
      ]
    },
    {
      "type": "rich_text_list",
      "style": "bullet",
      "indent": 0,
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [{ "type": "text", "text": "Huddles" }]
        },
        {
          "type": "rich_text_section",
          "elements": [{ "type": "text", "text": "Canvas" }]
        }
      ]
    }
  ]
}
```

A card block. Its `title`, `subtitle`, `body` and `subtext` are text objects even though the field
table types them as String, and `slack_icon` carries `"type": "icon"`, not `"type": "slack_icon"`:

```blockkit
{
  "type": "card",
  "slack_icon": {
    "type": "icon",
    "name": "sparkle"
  },
  "title": {
    "type": "mrkdwn",
    "text": "Lumon Industries"
  },
  "body": {
    "type": "mrkdwn",
    "text": "Please enjoy each card equally."
  }
}
```

A plan block. Its `title` is a **bare string** — the opposite of the card block above — `pending` is
available on a task only because the task is nested here, and the emoji is an element rather than a
`:shortcode:` in the text:

```blockkit
{
  "type": "plan",
  "title": "Analysing the paper",
  "tasks": [
    {
      "task_id": "fetch",
      "title": "Fetched the source",
      "status": "complete",
      "details": {
        "type": "rich_text",
        "elements": [
          {
            "type": "rich_text_section",
            "elements": [
              { "type": "emoji", "name": "white_check_mark" },
              { "type": "text", "text": " 24 pages, 3 figures" }
            ]
          }
        ]
      }
    },
    {
      "task_id": "summarise",
      "title": "Summarising the argument",
      "status": "in_progress"
    },
    {
      "task_id": "review",
      "title": "Checking the citations",
      "status": "pending"
    }
  ]
}
```

## Known gaps and ambiguities in the source documentation

These are properties of Slack's published reference, re-checked against it directly. Where an item
is marked as verified against a live workspace, it was established by posting the payload and
reading the response, and it stands over the published reference. Where it is marked untested, the
measurement stops where the note says it stops and has not been rounded up into a rule.

- The **Slack icon object** is missing from the composition-objects index. Its reference page is
  published and appears in the documentation sitemap, but the only link to it anywhere is the
  `slack_icon` row of the card block's field table. It is documented in
  `references/composition-objects.md` regardless; working from the index alone would omit it.
- The composition-objects index links to an **input parameter object** page that is still not
  published: the link 404s and the page is still absent from the documentation sitemap. Its entry
  in `references/composition-objects.md` is reconstructed from the worked example on the trigger
  object page, which is the only place its shape appears, and is marked as such.
- **Settled, verified against a live workspace.** Each of the following was established by posting
  the payload to a real workspace and reading back the API's response and the rendered result.
  Where one of them contradicts Slack's published reference, it overrides it, and the type cells
  and enum descriptions in `references/` are corrected in place with the source's own wording noted
  beside them. Each is recorded in full at the entry for the block or element concerned.
  - The card block types `title`, `subtitle`, `body` and `subtext` as "String". They are text
    objects. A bare string is refused with `invalid_blocks: must provide an object`, and the
    identical card with `{"type": "mrkdwn", "text": "..."}` in each field is accepted. All four
    render mrkdwn, links included.
  - `plan.title` is typed "Object" and described as plain text. It is a **bare string**. A text
    object is refused with `invalid_blocks: must provide a string`. This is the opposite of the
    card block above, and the two are recorded pointing at each other for that reason.
  - `task_card.status` accepts a different set of values depending on where the block sits. A
    top-level `task_card` takes `in_progress`, `complete` and `error`; a task nested in a `plan`
    block's `tasks` also takes `pending`. `pending` is documented as valid and is refused on a
    top-level card with `invalid_blocks: must be a valid enum value` — which makes Slack's own
    example for the block invalid as written. `in-progress` with a hyphen, `done` and `running` are
    refused in both positions. The reading that "queued, not started" means something as a row of a
    plan and nothing for a card standing alone is inference, and is marked as such where it appears.
  - The `plan` block accepts an undocumented `status` field, and it is inert. All four task
    statuses are accepted on it and none changes what renders; the plan's displayed state is
    derived from its task cards. Do not set it — set the children's statuses and the plan follows.
  - `details` and `output` on a task card render almost identically: the same body text under the
    title, with `output` adding a leading dot at a slightly different indent. Both take a single
    `rich_text` entity. There is no disclosure control and no separate panel. Choose one; there is
    no reason to set both unless that indent is wanted.
  - A `rich_text` `text` element does not parse emoji shortcodes; `mrkdwn` in a `section` does. Use
    the `emoji` element in rich text.
- **Verified but not generalised** — an observed rejection whose rule is untested:
  - A multiplication sign `×` (U+00D7) inside a `rich_text` `text` element was refused with
    `invalid_blocks`; the same payload with `x` in its place was accepted. Which characters outside
    ASCII are affected, and why, is **untested** — this is not a claim that non-ASCII is rejected,
    and unicode emoji are known to render. Recorded at the text element as one observed rejection.
- **Measured floors, not limits** — a value that was reached, with nothing said about the ceiling:
  - A `plan` block's `tasks` holds at least **12** task cards with no error; a long plan folds in
    the client. Slack documents no limit. The upper bound is **untested**.
- **Still open** — Slack's field table and Slack's own example for the same field disagree, and
  only the example has been confirmed by use:
  - `alert.text` is typed "String"; the block's example passes a text object.
  - `alert.level` is typed "Array"; it is a single string from the enum `default`, `info`,
    `warning`, `error`, `success`.
  - `container.title` and `container.subtitle` are typed "String"; the block's example passes text
    objects. `container.rich_text_title` is typed "String" while its description calls for a
    `rich_text` block.
  - `card.actions` is typed as an actions block; the block's example passes a bare array of button
    elements.

  Where a table and an example disagree, the example is the more reliable of the two.
- "Array" and "Object" in a type cell say nothing about what is inside. `data_table.rows` is an
  array of arrays of cell objects; `context_actions.elements` is an array of two specific element
  types; `carousel.elements` is an array of card blocks. The description, and then the example,
  is where the element type is actually stated.
- Field tables occasionally omit the requiredness cell entirely (for example `verbatim` on the
  text object). Those are optional fields.
