# Blocks

Blocks are the top-level containers in a Block Kit payload. A message carries up to 50 blocks in its `blocks` array; a modal or Home tab carries up to 100.

## Contents

- Actions block — `actions`
- Alert block — `alert`
- Card block — `card`
- Carousel block — `carousel`
- Container block — `container`
- Context actions block — `context_actions`
- Context block — `context`
- Data table block — `data_table`
- Data visualization block — `data_visualization`
- Divider block — `divider`
- File block — `file`
- Header block — `header`
- Image block — `image`
- Input block — `input`
- Markdown block — `markdown`
- Plan block — `plan`
- Rich text block — `rich_text`
- Section block — `section`
- Table block — `table`
- Task card block — `task_card`
- Video block — `video`

---

## Actions block — `actions`

Holds multiple interactive elements.

- **Surfaces:** Messages, Modals, Home tabs
- **Compatible elements:** Button, Checkboxes, Date picker, Datetime picker, Multi-select menu, Overflow menu, Radio button, Rich text input, Select menu, Time picker, Workflow buttons

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For an actions block, `type` is always `actions`. |
| `elements` | Object[] | Required | An array of interactive [element objects](https://docs.slack.dev/reference/block-kit/block-elements) - [buttons](https://docs.slack.dev/reference/block-kit/block-elements/button-element), [select menus](https://docs.slack.dev/reference/block-kit/block-elements/select-menu-element), [overflow menus](https://docs.slack.dev/reference/block-kit/block-elements/overflow-menu-element), or [date pickers](https://docs.slack.dev/reference/block-kit/block-elements/date-picker-element). There is a maximum of 25 elements in each action block. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, a `block_id` will be generated. You can use this `block_id` when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |

### Examples

**Example 1**: An actions block with a select menu and a button:

```blockkit
{
  "blocks": [
    {
      "type": "actions",
      "block_id": "actions1",
      "elements": [
        {
          "type": "static_select",
          "placeholder": {
            "type": "plain_text",
            "text": "Which witch is the witchiest witch?"
          },
          "action_id": "select_2",
          "options": [
            {
              "text": {
                "type": "plain_text",
                "text": "Matilda"
              },
              "value": "matilda"
            },
            {
              "text": {
                "type": "plain_text",
                "text": "Glinda"
              },
              "value": "glinda"
            },
            {
              "text": {
                "type": "plain_text",
                "text": "Granny Weatherwax"
              },
              "value": "grannyWeatherwax"
            },
            {
              "text": {
                "type": "plain_text",
                "text": "Hermione"
              },
              "value": "hermione"
            }
          ]
        },
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "Cancel"
          },
          "value": "cancel",
          "action_id": "button_1"
        }
      ]
    }
  ]
}
```

**Example 2**: An actions block with a datepicker, an overflow, and a button:

```blockkit
{
  "blocks": [
    {
      "type": "actions",
      "block_id": "actionblock789",
      "elements": [
        {
          "type": "datepicker",
          "action_id": "datepicker123",
          "initial_date": "1990-04-28",
          "placeholder": {
            "type": "plain_text",
            "text": "Select a date"
          }
        },
        {
          "type": "overflow",
          "options": [
            {
              "text": {
                "type": "plain_text",
                "text": "*this is plain_text text*"
              },
              "value": "value-0"
            },
            {
              "text": {
                "type": "plain_text",
                "text": "*this is plain_text text*"
              },
              "value": "value-1"
            },
            {
              "text": {
                "type": "plain_text",
                "text": "*this is plain_text text*"
              },
              "value": "value-2"
            },
            {
              "text": {
                "type": "plain_text",
                "text": "*this is plain_text text*"
              },
              "value": "value-3"
            },
            {
              "text": {
                "type": "plain_text",
                "text": "*this is plain_text text*"
              },
              "value": "value-4"
            }
          ],
          "action_id": "overflow"
        },
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "Click Me"
          },
          "value": "click_me_123",
          "action_id": "button"
        }
      ]
    }
  ]
}
```


## Alert block — `alert`

Displays alerts, warnings, and informational messages.

- **Surfaces:** Modals

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For an alert block, `type` is always `alert`. |
| `text` | String | Required | The alert message, using `plain_text` or `mrkdwn` formatting. Maximum 200 characters. |
| `level` | Array | Optional | One of `default`, `info`, `warning`, `error`, or `success`. Will be `default` if omitted. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, a `block_id` will be generated. |

Alert blocks are currently only supported in modals.

### Example

A sample alert block:

```blockkit
{
  "blocks": [
    {
      "type": "alert",
      "text": {
        "type": "mrkdwn",
        "text": "The work is mysterious and important.",
        "verbatim": false
      },
      "level": "info"
    }
  ]
}
```


## Card block — `card`

Displays content in a card.

- **Surfaces:** Messages, Modals, Home tabs
- **Compatible elements:** Button

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a card block, `type` is always `card`. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, a `block_id` will be generated. |
| `hero_image` | [Image element](https://docs.slack.dev/reference/block-kit/block-elements/image-element) | Optional | Link to the top image used on the card. Max length 3000 characters. The `alt_text` property has a max length of 2000 characters. |
| `icon` | [Image element](https://docs.slack.dev/reference/block-kit/block-elements/image-element) | Optional | Link to the small image used next to the card's title and subtitle. Max length 3000 characters. The `alt_text` property has a max length of 2000 characters. |
| `title` | [Text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) | Optional | Title of the card, using `plain_text` or `mrkdwn` formatting. 150 characters max. Slack's own table types this `String`; it is a text object. See "Text fields on a card" below. |
| `subtitle` | [Text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) | Optional | Subtitle of the card, using `plain_text` or `mrkdwn` formatting. 150 characters max. Slack's own table types this `String`; it is a text object. |
| `body` | [Text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) | Optional | Content of the card, using `plain_text` or `mrkdwn` formatting. 200 characters max. Slack's own table types this `String`; it is a text object. |
| `actions` | [Actions block](https://docs.slack.dev/reference/block-kit/blocks/actions-block) | Optional | Action buttons shown at the bottom of the card, maximum of 3 buttons. Buttons with `danger` style will be left-aligned, while buttons with `primary` or no style will be right-aligned (buttons with `primary` style will be furthest to the right). |
| `slack_icon` | [Slack icon composition object](https://docs.slack.dev/reference/block-kit/composition-objects/slack-icon-object) | Optional | A Slack icon to be rendered next to the card's title and subtitle. Mutually exclusive with `icon`, that is, only one of `icon` & `slack_icon` can be present as they render in the same location on the card. |
| `subtext` | [Text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) | Optional | Subtext to be rendered below body of the card, using `plain_text` or `mrkdwn` formatting. Maximum 200 characters. Slack's own table types this `String`; it is a text object. |

At least one of `hero_image`, `title`, `actions`, or `body` is required.

Note that there is not currently an attribute to define the size of the card.

`actions` is typed as an [actions block](https://docs.slack.dev/reference/block-kit/blocks/actions-block), but the block's own example passes a bare array of button elements rather than an object with `"type": "actions"`. Follow the example. Maximum 3 buttons.

### Text fields on a card

`title`, `subtitle`, `body` and `subtext` are [text objects](https://docs.slack.dev/reference/block-kit/composition-objects/text-object), not strings, even though Slack's field table types all four as `String`. Passing a bare string is rejected, and the rejection takes the whole message down:

```
invalid_blocks: must provide an object [json-pointer:/blocks/1/elements/0/title]
```

This is verified against a live workspace, not inferred: a card whose text fields are bare strings is refused, and the same card with `{"type": "mrkdwn", "text": "..."}` in each of them is accepted. All four fields render `mrkdwn`, including links.

The block's own example below uses text objects throughout. Where this block's type column and its example disagree, the example is correct.

**The rule does not generalise.** The plan block goes the other way: `plan.title` is typed `Object` and requires a bare string, and a text object there is refused with `must provide a string`. "The field table is wrong, pass a text object" is not a rule about Block Kit — it is a fact about this block. Look each field up.

### Icons on a card

A card shows at most one icon next to its title and subtitle, and there are two mutually exclusive ways to set it:

- `icon` — an [image element](https://docs.slack.dev/reference/block-kit/block-elements/image-element), for an image fetched from a URL.
- `slack_icon` — a [Slack icon object](https://docs.slack.dev/reference/block-kit/composition-objects/slack-icon-object), for one of Slack's built-in icons.

Supplying both is an error, because they render in the same position.

The Slack icon object is `{"type": "icon", "name": "sparkle"}`. Its `type` is the literal string `icon`, not `slack_icon` — `slack_icon` names the card field, not the object. The icon is chosen by `name`, and `name` must be one of exactly 54 documented values. The object is documented in `composition-objects.md` under "Slack icon object", which carries the full list of names; the values are not guessable and nothing outside that list is accepted.

### Examples

A sample card block:

```blockkit
{
  "blocks": [
    {
      "type": "card",
      "icon": {
        "type": "image",
        "image_url": "https://picsum.photos/36/36",
        "alt_text": "Icon"
      },
      "title": {
        "type": "mrkdwn",
        "text": "Lumon Industries",
        "verbatim": false
      },
      "subtitle": {
        "type": "mrkdwn",
        "text": "Committed to work-life balance",
        "verbatim": false
      },
      "hero_image": {
        "type": "image",
        "image_url": "https://picsum.photos/400/300",
        "alt_text": "Sample hero image"
      },
      "body": {
        "type": "mrkdwn",
        "text": "Please enjoy each card equally.",
        "verbatim": false
      },
      "actions": [
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "Action Button",
            "emoji": false
          },
          "action_id": "button_action"
        }
      ]
    }
  ]
}
```

A card using a built-in Slack icon instead of an image, and carrying `subtext`. Note that every one of the four text fields is a text object:

```blockkit
{
  "blocks": [
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
      "subtitle": {
        "type": "mrkdwn",
        "text": "Committed to work-life balance"
      },
      "body": {
        "type": "mrkdwn",
        "text": "Please enjoy each card equally. See the <https://example.com|handbook> for details."
      },
      "subtext": {
        "type": "mrkdwn",
        "text": "Praise Kier."
      }
    }
  ]
}
```


## Carousel block — `carousel`

Displays related card blocks in a horizontally-scrolling container.

- **Surfaces:** Messages, Home tabs

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a carousel block, `type` is always `carousel`. |
| `elements` | Array | Required | A list of cards. The carousel must contain at least one card, with a maximum of 10 cards. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, a `block_id` will be generated. |

### Example

A sample carousel block:

```blockkit
{
  "blocks": [
    {
      "type": "carousel",
      "elements": [
        {
          "type": "card",
          "block_id": "carousel-card-1",
          "icon": {
            "type": "image",
            "image_url": "https://picsum.photos/36/36",
            "alt_text": "Icon"
          },
          "title": {
            "type": "mrkdwn",
            "text": "MDR",
            "verbatim": false
          },
          "subtitle": {
            "type": "mrkdwn",
            "text": "Refining data files",
            "verbatim": false
          },
          "hero_image": {
            "type": "image",
            "image_url": "https://picsum.photos/400/300",
            "alt_text": "Sample hero image"
          },
          "body": {
            "type": "mrkdwn",
            "text": "Blue badge required to gain access.",
            "verbatim": false
          },
          "actions": [
            {
              "type": "button",
              "text": {
                "type": "plain_text",
                "text": "Action Button",
                "emoji": false
              },
              "action_id": "button_action_1"
            }
          ]
        },
        {
          "type": "card",
          "block_id": "carousel-card-2",
          "icon": {
            "type": "image",
            "image_url": "https://picsum.photos/36/36",
            "alt_text": "Icon"
          },
          "title": {
            "type": "mrkdwn",
            "text": "O&D",
            "verbatim": false
          },
          "subtitle": {
            "type": "mrkdwn",
            "text": "Storage, maintenance, and rotation of art pieces",
            "verbatim": false
          },
          "hero_image": {
            "type": "image",
            "image_url": "https://picsum.photos/400/300",
            "alt_text": "Sample hero image"
          },
          "body": {
            "type": "mrkdwn",
            "text": "Green badge required to gain access.",
            "verbatim": false
          },
          "actions": [
            {
              "type": "button",
              "text": {
                "type": "plain_text",
                "text": "Action Button",
                "emoji": false
              },
              "action_id": "button_action_2"
            }
          ]
        },
        {
          "type": "card",
          "block_id": "carousel-card-3",
          "icon": {
            "type": "image",
            "image_url": "https://picsum.photos/36/36",
            "alt_text": "Icon"
          },
          "title": {
            "type": "mrkdwn",
            "text": "Wellness Center",
            "verbatim": false
          },
          "subtitle": {
            "type": "mrkdwn",
            "text": "Wellness sessions",
            "verbatim": false
          },
          "hero_image": {
            "type": "image",
            "image_url": "https://picsum.photos/400/300",
            "alt_text": "Sample hero image"
          },
          "body": {
            "type": "mrkdwn",
            "text": "Please take a seat in the waiting room until called.",
            "verbatim": false
          },
          "actions": [
            {
              "type": "button",
              "text": {
                "type": "plain_text",
                "text": "Action Button",
                "emoji": false
              },
              "action_id": "button_action_3"
            }
          ]
        }
      ]
    }
  ]
}
```


## Container block — `container`

A general-purpose wrapper for grouping child blocks together, with a configurable size.

- **Surfaces:** Messages, Home tabs

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a container block, `type` is always `container`. |
| `title` | String | Optional | Title of the container, using `plain_text` formatting. Maximum of 150 characters. Optional (one of `title` or `rich_text_title` is required) |
| `rich_text_title` | String | Optional | The title for the container as a [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. If both `title` and `rich_text_title` are provided, `rich_text_title` takes precedence. Optional (one of `title` or `rich_text_title` is required) |
| `subtitle` | String | Optional | Subtitle of the container, using `plain_text` or `mrkdwn` formatting. Maximum of 150 characters. |
| `child_blocks` | Array | Required | List of included blocks. Maximum of 10 blocks. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, a `block_id` will be generated. |
| `width` | String | Optional | Sets the width of the container block. The `narrow`, `standard`, and `wide` options use a platform-determined constrained width. The `full` option expands to fill the available space. Default is `standard`. |
| `icon` | [Image element](https://docs.slack.dev/reference/block-kit/block-elements/image-element) | Optional | Link to the small image used next to the card's title and subtitle. Maximum length of 3000 characters. The `alt_text` property has a maximum length of 2000 characters. |
| `is_collapsible` | Boolean | Optional | When `true`, the block can be collapsed to show only the title. Defaults to `false`. |
| `default_collapsed` | Boolean | Optional | When `true` and `is_collapsible` are both `true`, the block initially renders in a collapsed state. Defaults to `false`. |
| `has_header_divider` | Boolean | Optional | When true, a visible border is rendered below the header to visually separate it from the content. Only applies when the block is not collapsible. Defaults to `false`. |

The `title` and `subtitle` type cells above read `String`, but the block's own example passes text objects for both, and `rich_text_title` is typed `String` while its description calls for a [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. Follow the example and the descriptions rather than the type column; the card block's equivalent fields behave the same way and are confirmed to require text objects.

### Supported child blocks

- [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block)
- [context](https://docs.slack.dev/reference/block-kit/blocks/context-block)
- [divider](https://docs.slack.dev/reference/block-kit/blocks/divider-block)
- [file](https://docs.slack.dev/reference/block-kit/blocks/file-block)
- [header](https://docs.slack.dev/reference/block-kit/blocks/header-block)
- [image](https://docs.slack.dev/reference/block-kit/blocks/image-block)
- [input](https://docs.slack.dev/reference/block-kit/blocks/input-block)
- [rich_text](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block)
- [section](https://docs.slack.dev/reference/block-kit/blocks/section-block)
- [table](https://docs.slack.dev/reference/block-kit/blocks/table-block)
- [video](https://docs.slack.dev/reference/block-kit/blocks/video-block)

### Example

A sample container block:

```blockkit
{
  "blocks": [
    {
      "type": "container",
      "block_id": "bkb_container_bulk_update",
      "title": {
        "type": "plain_text",
        "text": "Bulk update: 2 records selected"
      },
      "subtitle": {
        "type": "plain_text",
        "text": "Review changes before confirming"
      },
      "is_collapsible": true,
      "child_blocks": [
        {
          "type": "section",
          "block_id": "record-row-1",
          "text": {
            "type": "mrkdwn",
            "text": "*DCW-1024*\nStatus: Open → Closed\nAssignee: @princessdonut → @carl"
          }
        },
        {
          "type": "divider",
          "block_id": "bulk-div-1"
        },
        {
          "type": "section",
          "block_id": "record-row-2",
          "text": {
            "type": "mrkdwn",
            "text": "*DCW-1025*\nStatus: In Progress → Closed\nAssignee: @mordecai → @carl"
          }
        },
        {
          "type": "divider",
          "block_id": "bulk-div-2"
        },
        {
          "type": "context",
          "block_id": "bulk-status-bar",
          "elements": [
            {
              "type": "mrkdwn",
              "text": ":white_check_mark: 2 records will be updated • Status → Closed • Assignee → @carl"
            }
          ]
        },
        {
          "type": "actions",
          "block_id": "bulk-actions",
          "elements": [
            {
              "type": "button",
              "text": {
                "type": "plain_text",
                "text": "Confirm All",
                "emoji": true
              },
              "style": "primary",
              "action_id": "bulk_confirm"
            },
            {
              "type": "button",
              "text": {
                "type": "plain_text",
                "text": "Cancel",
                "emoji": true
              },
              "action_id": "bulk_cancel"
            }
          ]
        }
      ]
    }
  ]
}
```


## Context actions block — `context_actions`

Displays actions as contextual info, which can include both feedback buttons and icon buttons.

- **Surfaces:** Messages
- **Compatible elements:** Feedback buttons, Icon button

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a context actions block, `type` is always `context_actions`. |
| `elements` | Object[] | Required | An array of [feedback buttons elements](https://docs.slack.dev/reference/block-kit/block-elements/feedback-buttons-element) and [icon button elements](https://docs.slack.dev/reference/block-kit/block-elements/icon-button-element). Maximum number of items is 5. |
| `block_id` | String | Optional | A unique identifier for a block. You can use this `block_id` when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). If not specified, `block_id` will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |

### Examples

**Example 1**: Context actions block with [feedback buttons](https://docs.slack.dev/reference/block-kit/block-elements/feedback-buttons-element):

```blockkit
{
  "blocks": [
    {
      "type": "context_actions",
      "elements": [
        {
          "type": "feedback_buttons",
          "action_id": "feedback_buttons_1",
          "positive_button": {
            "text": {
              "type": "plain_text",
              "text": "👍"
            },
            "value": "positive_feedback"
          },
          "negative_button": {
            "text": {
              "type": "plain_text",
              "text": "👎"
            },
            "value": "negative_feedback"
          }
        }
      ]
    }
  ]
}
```

**Example 2**: Context actions block with an [icon button](https://docs.slack.dev/reference/block-kit/block-elements/icon-button-element):

```blockkit
{
  "blocks": [
    {
      "type": "context_actions",
      "elements": [
        {
          "type": "icon_button",
          "icon": "trash",
          "text": {
            "type": "plain_text",
            "text": "Delete"
          },
          "action_id": "delete_button_1",
          "value": "delete_item"
        }
      ]
    }
  ]
}
```


## Context block — `context`

Provides contextual info, which can include both images and text.

- **Surfaces:** Messages, Modals, Home tabs
- **Compatible elements:** Image

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a context block, `type` is always `context`. |
| `elements` | Object[] | Required | An array of [image elements](https://docs.slack.dev/reference/block-kit/block-elements/image-element) and [text objects](https://docs.slack.dev/reference/block-kit/composition-objects/text-object). Maximum number of items is 10. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, one will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |

### Examples

```blockkit
{
  "blocks": [
    {
      "type": "context",
      "elements": [
        {
          "type": "image",
          "image_url": "https://image.freepik.com/free-photo/red-drawing-pin_1156-445.jpg",
          "alt_text": "images"
        },
        {
          "type": "mrkdwn",
          "text": "Location: **Dogpatch**"
        }
      ]
    }
  ]
}
```


## Data table block — `data_table`

Displays rich tables that support pagination, sorting, filtering, and interactivity.

- **Surfaces:** Messages, Home tabs

The data table block is a rich table that supports pagination, sorting, filtering, and rich interactivity, such as opening a [Work Object flexpane](https://docs.slack.dev/messaging/work-objects-overview#flexpane) or clickable links in cells. This is different from the existing [table block](https://docs.slack.dev/reference/block-kit/blocks/table-block), which only supports filtering and basic interactivity.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a data table block, `type` is always `data_table`. |
| `rows` | Array | Required | An array consisting of table rows. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, a `block_id` will be generated. |
| `page_size` | Integer | Optional | Number of rows per page. Min `1`, Max `100`. Defaults to `5` if omitted. |
| `caption` | String | Required | A caption for the table; used as the value for the HTML caption element. |
| `row_header_column_index` | Integer | Optional | The 0-based index of the column that uniquely identifies each row (the row header). This column is treated as the row's primary identifier for screen readers. Defaults to 0 if omitted. |

### Usage info

You can use `rich_text`, `raw_text` (simple text), or `raw_number` (numeric values) for cell content. The first row of the table is a header, and `rich_text` cannot be used for header cells. You can have a minimum of 2 rows (1 regular row plus the header) and a maximum of 201 rows (200 regular rows plus the header). All rows must have the same number of values.

A single table's character count across all cells cannot exceed 20,000 characters. Additionally, the aggregate character count across all table cells for a single message cannot exceed 20,000 characters. Large tables should be broken up into separate messages.

Sorting rows by column is done alphabetically by default. If a column contains cells all of type `raw_number`, a numeric sort will be performed instead. You can have a minimum of 1 column and a maximum of 20 columns.

### Schema for raw_text

```blockkit
"properties": {
  "type": {
    "type": "string",
    "enum": [
      "raw_text"
    ]
  },
  "text": {
    "type": "string",
    "minLength": 1
  }
}
```

### Schema for raw_number

```blockkit
"properties": {
  "type": {
    "type": "string",
    "enum": [
      "raw_number"
    ]
  },
  "value": {
    "type": "number"
  },
  "text": {
    "type": "string",
    "minLength": 1
  }
}
```

### Example

A sample data table block:

```blockkit
{
  "blocks": [
    {
      "type": "data_table",
      "caption": "A Fabulous Table",
      "rows": [
        [
          {
            "type": "raw_text",
            "text": "Name"
          },
          {
            "type": "raw_text",
            "text": "Department"
          },
          {
            "type": "raw_text",
            "text": "Badge"
          }
        ],
        [
          {
            "type": "raw_text",
            "text": "Data Refinement Department"
          },
          {
            "type": "raw_text",
            "text": "MDR"
          },
          {
            "type": "rich_text",
            "elements": [
              {
                "type": "rich_text_section",
                "elements": [
                  {
                    "type": "text",
                    "text": "Blue",
                    "style": {
                      "bold": true
                    }
                  }
                ]
              }
            ]
          }
        ],
        [
          {
            "type": "raw_text",
            "text": "Art Sourcing Department"
          },
          {
            "type": "raw_text",
            "text": "O&D"
          },
          {
            "type": "rich_text",
            "elements": [
              {
                "type": "rich_text_section",
                "elements": [
                  {
                    "type": "text",
                    "text": "Green"
                  },
                  {
                    "type": "text",
                    "text": "review",
                    "style": {
                      "italic": true
                    }
                  }
                ]
              }
            ]
          }
        ],
        [
          {
            "type": "raw_text",
            "text": "Wellness Department"
          },
          {
            "type": "raw_text",
            "text": "Wellness Center"
          },
          {
            "type": "rich_text",
            "elements": [
              {
                "type": "rich_text_section",
                "elements": [
                  {
                    "type": "text",
                    "text": "Limited",
                    "style": {
                      "bold": true
                    }
                  }
                ]
              }
            ]
          }
        ]
      ]
    }
  ]
}
```


## Data visualization block — `data_visualization`

Displays data visually in pie, bar, area, or line chart formats.

- **Surfaces:** Messages

The data visualization block allows you to display data in line, bar, area, or pie chart format.

There is a limit of 2 data visualization blocks per message.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a data visualization block, `type` is always `data_visualization`. |
| `title` | String | Required | A short label displayed above the chart. Maximum 50 characters. |
| `chart` | Object | Required | The chart-specific payload. Must be one of the following: `pie`, `bar`, `area`, or `line`. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, a `block_id` will be generated. |

### Pie

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of chart. In this case, `pie`. |
| `segments` | array of Segment | Required | Labeled slices that make up the pie. Min 1, max 12. |

### Bar

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of chart. In this case, `bar`. |
| `series` | array of Data Series | Required | Series to plot as bar groups. Min 1, max 12. For multiple series, bars are grouped by label. |
| `axis_config` | Axis Config | Required | X-axis categories and axis titles. |

### Area

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of chart. In this case, `area`. |
| `series` | array of Data Series | Required | Series to plot as filled areas. Min 1, max 12. Series are layered in array order (first at back). |
| `axis_config` | Axis Config | Required | X-axis categories and axis titles. |

### Line

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of chart. In this case, `line`. |
| `series` | array of Data Series | Required | Series to plot as lines. Min 1, max 12. |
| `axis_config` | Axis Config | Required | X-axis categories and axis titles. |

### Segment

| Field | Type | Required | Description |
|---|---|---|---|
| `label` | String | Required | Display name for this slice, shown in the legend and on hover. Maximum of 20 characters. |
| `value` | number | Required | Numeric weight of this slice. Must be greater than 0. Rendered percentage is the value divided by the sum of all segment values. |

### Data Series

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | String | Required | Human-readable identifier displayed in the chart legend. Must be unique across all series in the same chart. Maximum 20 characters. |
| `data` | array of Data Point | Required | Ordered data points. Min 1, max 20. Must contain exactly one entry for every label in `axis_config.categories`. |

### Data Point

| Field | Type | Required | Description |
|---|---|---|---|
| `label` | String | Required | The x-axis category this point belongs to. Must match one of the values in axis_config.categories. Maximum of 20 characters. |
| `value` | number | Required | Numeric y-axis value. Negative values are permitted. |

### Axis Config

| Field | Type | Required | Description |
|---|---|---|---|
| `categories` | array of strings | Required | Category labels for the x-axis. Defines valid labels and their left-to-right display order. Each category label has a maximum of 20 characters. |
| `x_label` | String | Optional | Descriptive title displayed below the x-axis (e.g., "Time of Day"). Maximum of 50 characters. |
| `y_label` | String | Optional | Descriptive title displayed beside the y-axis (e.g., "Latency (ms)"). Maximum of 50 characters. |

### Validation rules (enforced at runtime)

| Rule | Description |
|---|---|
| Label matching | Every `data_point.label` in every series must match a value in `axis_config.categories.` Series may not omit data points. |
| Unique series names | Each series within a chart must have a distinct name. |
| Category ordering | The order of `axis_config.categories` defines the x-axis display order. |

### Examples

A sample pie chart payload:

```blockkit
{
  "type": "data_visualization",
  "title": "My Favorite Candy Bars",
  "chart": {
    "type": "pie",
    "segments": [
      {
        "label": "Kit Kat",
        "value": 45
      },
      {
        "label": "Twix",
        "value": 28
      },
      {
        "label": "Crunch",
        "value": 18
      },
      {
        "label": "Milky Way",
        "value": 9
      }
    ]
  }
}
```

A sample bar chart payload:

```blockkit
{
  "type": "data_visualization",
  "title": "My Favorite Pies by Percentage of Tastiness",
  "chart": {
    "type": "bar",
    "series": [
      {
        "name": "Pies",
        "data": [
          {
            "label": "Strawberry Rhubarb",
            "value": 85
          },
          {
            "label": "Pumpkin",
            "value": 70
          },
          {
            "label": "Lemon Meringue",
            "value": 72
          },
          {
            "label": "Blueberry",
            "value": 90
          },
          {
            "label": "Key Lime",
            "value": 56
          }
        ]
      }
    ],
    "axis_config": {
      "categories": [
        "Strawberry Rhubarb",
        "Pumpkin",
        "Lemon Meringue",
        "Blueberry",
        "Key Lime"
      ],
      "x_label": "Pies",
      "y_label": "Percentage of Tastiness"
    }
  }
}
```

A sample area chart payload:

```blockkit
{
  "type": "data_visualization",
  "title": "Daily Active Users",
  "chart": {
    "type": "area",
    "series": [
      {
        "name": "Pied Piper Free Tier",
        "data": [
          {
            "label": "Mon",
            "value": 12000
          },
          {
            "label": "Tues",
            "value": 13500
          },
          {
            "label": "Wed",
            "value": 15200
          },
          {
            "label": "Thurs",
            "value": 14800
          },
          {
            "label": "Fri",
            "value": 16400
          }
        ]
      },
      {
        "name": "Pied Piper Paid Tier",
        "data": [
          {
            "label": "Mon",
            "value": 4500
          },
          {
            "label": "Tues",
            "value": 4800
          },
          {
            "label": "Wed",
            "value": 5100
          },
          {
            "label": "Thurs",
            "value": 5600
          },
          {
            "label": "Fri",
            "value": 6200
          }
        ]
      }
    ],
    "axis_config": {
      "categories": [
        "Mon",
        "Tues",
        "Wed",
        "Thurs",
        "Fri"
      ],
      "x_label": "Day",
      "y_label": "Users"
    }
  }
}
```

A sample line chart payload:

```blockkit
{
  "type": "data_visualization",
  "title": "Weekly Paper Sales",
  "chart": {
    "type": "line",
    "series": [
      {
        "name": "Dunder Mifflin Infinity Website",
        "data": [
          {
            "label": "Week 1",
            "value": 32000
          },
          {
            "label": "Week 2",
            "value": 35000
          },
          {
            "label": "Week 3",
            "value": 29000
          },
          {
            "label": "Week 4",
            "value": 41000
          },
          {
            "label": "Week 5",
            "value": 45000
          }
        ]
      },
      {
        "name": "Dunder Mifflin In-store",
        "data": [
          {
            "label": "Week 1",
            "value": 32000
          },
          {
            "label": "Week 2",
            "value": 35000
          },
          {
            "label": "Week 3",
            "value": 29000
          },
          {
            "label": "Week 4",
            "value": 41000
          },
          {
            "label": "Week 5",
            "value": 45000
          }
        ]
      }
    ],
    "axis_config": {
      "categories": [
        "Week 1",
        "Week 2",
        "Week 3",
        "Week 4",
        "Week 5"
      ],
      "x_label": "Week",
      "y_label": "Paper Sales (USD)"
    }
  }
}
```


## Divider block — `divider`

Visually separates pieces of info inside of a message.

- **Surfaces:** Messages, Modals, Home tabs

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a divider block, `type` is always `divider`. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, one will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |

### Usage Info

A content divider, like an `<hr>`, to split up different blocks inside of a message. The divider block is nice and neat, requiring only a `type`.

### Examples

```blockkit
{
  "blocks": [
    {
      "type": "divider"
    }
  ]
}
```


## File block — `file`

Displays info about remote files.

- **Surfaces:** Messages

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a file block, `type` is always `file`. |
| `external_id` | String | Required | The external unique ID for this file. |
| `source` | String | Required | At the moment, `source` will always be `remote` for a remote file. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, one will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |

### Usage info

You can't add this block to app surfaces directly, but it will show up when [retrieving messages](https://docs.slack.dev/messaging/retrieving-messages) that contain remote files.

If you want to add remote files to messages, [follow our guide](https://docs.slack.dev/messaging/working-with-files#remote).

### Examples

```blockkit
{
  "blocks": [
    {
      "type": "file",
      "external_id": "ABCD1",
      "source": "remote"
    }
  ]
}
```


## Header block — `header`

Displays a larger-sized text.

- **Surfaces:** Messages, Modals, Home tabs

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For this block, type will always be `header`. |
| `text` | Object | Required | The text for the block, in the form of a [`plain_text` text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object). Maximum length for the `text` in this field is 150 characters. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, one will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |
| `level` | Integer | Optional | Set the level of the heading. Values `1`-`4` correspond to H1-H4 heading levels, respectively. |

### Usage info

A `header` is a plain-text block that displays in a larger, bold font. Use it to delineate between different groups of content in your app's surfaces.

### Examples

```blockkit
{
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "A Heartfelt Header"
      }
    }
  ]
}
```


## Image block — `image`

Displays an image.

- **Surfaces:** Messages, Modals, Home tabs

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For an image block, `type` is always `image`. |
| `alt_text` | String | Required | A plain-text summary of the image. This should not contain any markup. Maximum length for this field is 2000 characters. |
| `image_url` | String | Optional | The URL for a publicly hosted image. You must provide either an `image_url` or `slack_file`. Maximum length for this field is 3000 characters. |
| `slack_file` | Object | Optional | A [Slack image file object](https://docs.slack.dev/reference/block-kit/composition-objects/slack-file-object) that defines the source of the image. |
| `title` | Object | Optional | An optional title for the image in the form of a [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) that can only be of `type: plain_text`. Maximum length for the `text` in this field is 2000 characters. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, one will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |

### Usage info

An image block, designed to make those cat photos really pop. Supported file types include `png`, `jpg`, `jpeg`, and `gif`.

### Examples

The following three examples show different ways to get the following result:

**Example 1**: An image block using `image_url`:

```blockkit
{
  "blocks": [
    {
      "type": "image",
      "title": {
        "type": "plain_text",
        "text": "Please enjoy this photo of a kitten"
      },
      "block_id": "image4",
      "image_url": "http://placekitten.com/500/500",
      "alt_text": "An incredibly cute kitten."
    }
  ]
}
```

**Example 2**: An image block using `slack_file` with a `url`:

```blockkit
{
  "blocks": [
    {
      "type": "image",
      "title": {
        "type": "plain_text",
        "text": "Please enjoy this photo of a kitten"
      },
      "block_id": "image4",
      "slack_file": {
        "url": "https://files.slack.com/files-pri/T0123456-F0123456/xyz.png"
      },
      "alt_text": "An incredibly cute kitten."
    }
  ]
}
```

**Example 3**: An image block using `slack_file` with a `id`:

```blockkit
{
  "blocks": [
    {
      "type": "image",
      "title": {
        "type": "plain_text",
        "text": "Please enjoy this photo of a kitten"
      },
      "block_id": "image4",
      "slack_file": {
        "id": "F0123456"
      },
      "alt_text": "An incredibly cute kitten."
    }
  ]
}
```


## Input block — `input`

Collects information from users via elements.

- **Surfaces:** Messages, Modals, Home tabs
- **Compatible elements:** Checkboxes, Date picker, Datetime picker, Email input, File input, Multi-select menu, Number input, Plain-text input, Radio button, Rich text input, Select menu, Time picker, URL input

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For an input block, `type` is always `input`. |
| `label` | Object | Required | A label that appears above an input element in the form of a [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) that must have `type` of `plain_text`. Maximum length for the `text` in this field is 2000 characters. |
| `element` | Object | Required | A block element. See [above](https://docs.slack.dev/reference/block-kit/blocks/input-block) for full list. |
| `dispatch_action` | Boolean | Optional | A boolean that indicates whether or not the use of elements in this block should dispatch a [`block_actions`](https://docs.slack.dev/reference/interaction-payloads/block_actions-payload) payload. Defaults to `false`. This field is incompatible with the [`file_input`](https://docs.slack.dev/reference/block-kit/block-elements/file-input-element) block element. If `dispatch_action` is set to `true` and a `file_input` block element is provided, an unsupported type error will be raised. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, one will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message or view and each iteration of a message or view. If a message or view is updated, use a new `block_id`. |
| `hint` | Object | Optional | An optional hint that appears below an input element in a lighter grey. It must be a [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) with a `type` of `plain_text`. Maximum length for the `text` in this field is 2000 characters. |
| `optional` | Boolean | Optional | A boolean that indicates whether the input element may be empty when a user submits the modal. Defaults to `false`. |

### Usage info

Read our guides to collecting input [in modals](https://docs.slack.dev/surfaces/modals#gathering_input) or [in Home tabs](https://docs.slack.dev/surfaces/app-home#gathering_input) to learn how input blocks pass information to your app.

### Examples

An input block containing a [plain-text input element](https://docs.slack.dev/reference/block-kit/block-elements/plain-text-input-element):

```blockkit
{
  "blocks": [
    {
      "type": "input",
      "element": {
        "type": "plain_text_input"
      },
      "label": {
        "type": "plain_text",
        "text": "Label",
        "emoji": true
      }
    }
  ]
}
```


## Markdown block — `markdown`

Displays formatted markdown.

- **Surfaces:** Messages

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a markdown block, `type` is always `markdown`. |
| `text` | String | Required | The standard markdown-formatted text. The cumulative limit for all `markdown` blocks in a single payload is 12,000 characters. |
| `block_id` | String | Optional | The `block_id` is ignored in markdown blocks and will not be retained. |

The following `markdown` types are supported in the `text` field.

| Markdown type | Example | Result |
|---|---|---|
| Bold | `` **this is bold** `` or `` __this is bold__ `` | bold text |
| Italic | `` *this text is italicized* `` or `` _this text is italicized_ `` | italic text |
| Bold and nested italic | `` **this text is _extremely_ important** `` | bold with italic inside |
| All bold and italic | `` ***all of this is important*** `` | bold italic text |
| Links | `` [my text](https://www.google.com) `` | a hyperlink |
| Lists (unordered) | `- first item` / `- second item` / `- third item` on separate lines | a bulleted list |
| Lists (ordered) | `1. first item` / `2. second item` / `3. third item` on separate lines | a numbered list |
| Strikethrough | `` ~~this is strikethrough text~~ `` | struck-through text |
| Headers (level 1) | `# Header 1` | Renders as a header. Note that all header levels are rendered at the same size. |
| Headers (level 2+) | `## Header 2`, `### Header 3`, etc. | Renders as a header. Note that all header levels are rendered at the same size. |
| In-line code | a backtick-wrapped span | inline code |
| Block quote | `> this is a block quote` | a quoted line |
| Code blocks | a triple-backtick fence around the code | a code block |
| Code blocks with syntax highlighting | a triple-backtick fence with a language, e.g. `python` | Renders as a code block with syntax highlighting for the specified language. |
| Dividers (horizontal rules) | `---` | Renders as a horizontal divider line. |
| Tables | a pipe table: header row, `\| ----- \| ----- \|` separator, then data rows | Renders as a formatted table. |
| Task lists | `- [ ] incomplete task` and `- [x] completed task` | Renders as a task list with checkboxes. |
| Images | `` ![Logo](https://example.com/logo.png) `` | Translated to hyperlink text, i.e. [Logo](https://example.com/logo.png) |
| Escaped special character | `` \*This is special text\* `` | The literal text, unformatted |

Special characters that can be escaped with a leading backslash: backslash, backtick,
asterisk, underscore, curly braces, square brackets, parentheses, hash mark, plus sign,
minus sign (hyphen), dot, exclamation mark, ampersand.

### Usage info

This block can be used with [apps that use platform AI features](https://docs.slack.dev/ai/) when you expect a markdown response from an LLM that can get lost in translation rendering in Slack. Providing it in a markdown block leaves the translating to Slack to ensure your message appears as intended. Note that passing a single block may result in multiple blocks after translation.

### Examples

```blockkit
{
  "blocks": [
    {
      "type": "markdown",
      "text": "**Lots of information here!!**"
    }
  ]
}
```


## Plan block — `plan`

Displays a collection of related tasks.

- **Surfaces:** Messages

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For this block, type will always be `plan`. |
| `title` | String | Required | Title of the plan, as a bare string in plain text. Slack's own table types this `Object`; it is a bare string, and a text object is refused. See "Title is a bare string" below. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, one will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |
| `tasks` | Array | Optional | A sequence of [task card blocks](https://docs.slack.dev/reference/block-kit/blocks/task-card-block). Each task represents a single action within the plan. At least 12 tasks are accepted; no upper bound is documented and none was found. See "How many tasks a plan holds" below. |
| `status` | String | Optional | Absent from Slack's field table, accepted by the API, and inert: setting it changes nothing that renders. See "The plan's own `status` does nothing" below. |

### Title is a bare string

`plan.title` is a bare string. Slack's field table types it `Object` and describes it as plain text, which reads as a call for a `plain_text` [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object). A text object is refused, and the refusal takes the whole message down:

```
"title": {"type": "plain_text", "text": "Analysing the paper"}
  -> invalid_blocks: must provide a string [json-pointer:/blocks/0/title]

"title": "Analysing the paper"
  -> accepted
```

This is verified against a live workspace, not inferred, and the block's own example below passes a bare string too.

**This is the exact opposite of the card block.** The card block types `title`, `subtitle`, `body` and `subtext` as `String` and requires text objects for all four; the plan block types `title` as `Object` and requires a bare string. Both blocks contradict their own documentation, in opposite directions, so the card block's rule does not generalise — knowing it will lead a reader to write the wrong thing here. Neither rule can be derived from the other or from the type cell; each field has to be looked up.

### The plan's own `status` does nothing

A `plan` accepts a `status` field that Slack does not document. All four of the task statuses — `pending`, `in_progress`, `complete`, `error` — are accepted on it without error, and none of them changes what is rendered. The plan's displayed state is derived from the statuses of the task cards in `tasks`.

Do not set it. Set the statuses of the children and the plan follows.

Only acceptance and rendering were tested. Whether the field is read for anything else is untested.

### How many tasks a plan holds

A plan with **12** task cards in `tasks` posts without error; the client folds a long plan rather than truncating it. Slack documents no limit on the array.

12 is a floor, not the limit: it is the largest plan that was posted, and no larger one was tried. Where the real ceiling is, and what happens at it, is untested.

### Examples

```blockkit
{
  "blocks": [
    {
      "type": "plan",
      "title": "Thinking completed",
      "tasks": [
        {
          "task_id": "call_001",
          "title": "Fetched user profile information",
          "status": "in_progress",
          "details": {
            "type": "rich_text",
            "block_id": "viMWO",
            "elements": [
              {
                "type": "rich_text_section",
                "elements": [
                  {
                    "type": "text",
                    "text": "Searched database..."
                  }
                ]
              }
            ]
          },
          "output": {
            "type": "rich_text",
            "block_id": "viMWO",
            "elements": [
              {
                "type": "rich_text_section",
                "elements": [
                  {
                    "type": "text",
                    "text": "Profile data loaded"
                  }
                ]
              }
            ]
          }
        },
        {
          "task_id": "call_002",
          "title": "Checked user permissions",
          "status": "pending"
        },
        {
          "task_id": "call_003",
          "title": "Generated comprehensive user report",
          "status": "complete",
          "output": {
            "type": "rich_text",
            "block_id": "crsk",
            "elements": [
              {
                "type": "rich_text_section",
                "elements": [
                  {
                    "type": "text",
                    "text": "15 data points compiled"
                  }
                ]
              }
            ]
          }
        }
      ]
    }
  ]
}
```


## Rich text block — `rich_text`

Displays formatted, structured representation of text.

- **Surfaces:** Messages, Modals, Home tabs

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a rich text block, `type` is always `rich_text`. |
| `elements` | Object[] | Required | An array of rich text objects - [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_preformatted`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-preformatted-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), and [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element). See linked elements for more details. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, one will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message or view and each iteration of a message or view. If a message or view is updated, use a new `block_id`. |

### Usage info

The rich text block is also the output of the Slack client's WYSIWYG message composer, so all messages sent by end-users will have this format. Use this block to include user-defined formatted text in your Block Kit payload. While it is possible to format text with `mrkdwn`, `rich_text` is strongly preferred and allows greater flexibility.

You might encounter a `rich_text` block in a message payload, as a built-in type in apps created with the Deno Slack SDK, or as output of the [`rich_text_input`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-input-element) block element.

Rich text blocks can be deeply nested. For instance: a `rich_text_list` can contain a `rich_text_section` which can contain bold style text. More details on how that works is shown in the examples on the pages for the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_preformatted`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-preformatted-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), and [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block elements.


## Section block — `section`

Displays text, possibly alongside elements.

- **Surfaces:** Messages, Modals, Home tabs
- **Compatible elements:** Button, Checkboxes, Date picker, Image, Multi-select menu, Overflow menu, Radio button, Select menu, Time picker, Workflow buttons

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For a section block, type will always be `section`. |
| `text` | Object | Preferred | The text for the block, in the form of a [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object). Minimum length for the `text` in this field is 1 and maximum length is 3000 characters. This field is not _required_ if a valid array of `fields` objects is provided instead. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, one will be generated. You can use this `block_id` when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |
| `fields` | Object[] | Maybe | Required if no `text` is provided. An array of [text objects](https://docs.slack.dev/reference/block-kit/composition-objects/text-object). Any text objects included with `fields` will be rendered in a compact format that allows for 2 columns of side-by-side text. Maximum number of items is 10. Maximum length for the `text` in each item is 2000 characters. |
| `accessory` | Object | Optional | One of the compatible [element objects](https://docs.slack.dev/reference/block-kit/blocks/section-block) noted above. Be sure to confirm the desired element works with `section`. |
| `expand` | Boolean | Optional | Whether or not this section block's text should always expand when rendered. If false or not provided, it may be rendered with a 'see more' option to expand and show the full text. For [AI Assistant apps](https://docs.slack.dev/ai), this allows the app to post long messages without users needing to click 'see more' to expand the message. |

### Usage info

A `section` can be used as a text block, in combination with text fields, or side-by-side with certain [block elements](https://docs.slack.dev/reference/block-kit/block-elements).

### Examples

**Example 1**: A text section block:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "A message *with some bold text* and _some italicized text_."
      }
    }
  ]
}
```

**Example 2**: A section block containing text fields:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "text": "A message *with some bold text* and _some italicized text_.",
        "type": "mrkdwn"
      },
      "fields": [
        {
          "type": "mrkdwn",
          "text": "High"
        },
        {
          "type": "plain_text",
          "emoji": true,
          "text": "Silly"
        }
      ]
    }
  ]
}
```

**Example 3**: A section block containing a datepicker element:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "text": "*Haley* has requested you set a deadline for finding a house",
        "type": "mrkdwn"
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
  ]
}
```


## Table block — `table`

Displays structured information in a table.

- **Surfaces:** Messages, Home tabs
- **Compatible elements:** Rich text input

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Required | Always "table". |
| `block_id` | string | Optional | A unique identifier for a block. If not specified, a `block_id` will be generated. You can use this `block_id` when you receive an interaction payload to identify the source of the action. Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |
| `rows` | array | Required | An array consisting of table rows. Maximum 100 rows. Each row object is an array with a max of 20 table cells. Table cells can have a type of `rich_text`, `raw_text`, or `raw_number`. |
| `column_settings` | array | Optional | An array describing column behavior. If there are fewer items in the `column_settings` array than there are columns in the table, then the items in the the `column_settings` array will describe the same number of columns in the table as there are in the array itself. Any additional columns will have the default behavior. Maximum 20 items. See below for column settings schema. |

### Schema for column_settings

| Field | Type | Required | Description |
|---|---|---|---|
| `align` | string | Optional | The alignment for items in this column. Can be `left`, `center`, or `right`. Defaults to `left` if not defined. |
| `is_wrapped` | boolean | Optional | Whether the contents of this column should be wrapped or not. Defaults to `false` if not defined. |

### Usage info

Apps can programmatically publish messages that include a table by providing a table block in the `attachments` or `blocks` fields of a [`chat.postMessage`](https://docs.slack.dev/reference/methods/chat.postMessage#arguments) request. These fields support a top-level table block with `rich_text`, `raw_text`, or `raw_number` options. Tables may include formatted text (bold text, emoji, mentions, hyperlinks, etc.) with a `rich_text` table cell block type, while a `raw_text` cell supports more basic characters and `raw_number` support numeric values. You must include a value for one of either the top-level blocks or text arguments in the message payload.

A single table's character count across all cells cannot exceed 10,000 characters. Additionally, the aggregate character count across all table cells for a single message cannot exceed 10,000 characters. Large tables should be broken up into separate messages.

The `column_settings` property lets you change text alignment and text wrapping behavior for table columns. In the `JSON` example below, the first column has text wrapping enabled and the second column right aligned. Use null to skip a column.

Below is an example attachments value that you should send as a URL-encoded string in your request inside the `blocks` array.

### Examples

```blockkit
{
  "blocks": [
    {
      "type": "table",
      "column_settings": [
        {
          "is_wrapped": true
        },
        {
          "align": "right"
        }
      ],
      "rows": [
        [
          {
            "type": "raw_text",
            "text": "Header A"
          },
          {
            "type": "raw_text",
            "text": "Header B"
          }
        ],
        [
          {
            "type": "raw_text",
            "text": "Data 1A"
          },
          {
            "type": "rich_text",
            "elements": [
              {
                "type": "rich_text_section",
                "elements": [
                  {
                    "text": "Data 1B",
                    "type": "link",
                    "url": "https://slack.com"
                  }
                ]
              }
            ]
          }
        ],
        [
          {
            "type": "raw_text",
            "text": "Data 2A"
          },
          {
            "type": "rich_text",
            "elements": [
              {
                "type": "rich_text_section",
                "elements": [
                  {
                    "text": "Data 2B",
                    "type": "link",
                    "url": "https://slack.com"
                  }
                ]
              }
            ]
          }
        ]
      ]
    }
  ]
}
```

Support coming soon!


## Task card block — `task_card`

Displays a single task, representing a single action.

- **Surfaces:** Messages
- **Compatible elements:** URL source

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of block. For this block, type will always be `task_card`. |
| `task_id` | String | Required | ID for the task. |
| `title` | String | Required | Title of the task in plain text. A genuine bare string, unlike the card block's `title`. |
| `details` | Object | Optional | Details of the task in the form of a single [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) entity. Renders almost identically to `output`; see "`details` and `output` are the same panel" below. |
| `output` | Object | Optional | Output of the task in the form of a single [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) entity. Renders almost identically to `details`; see below. |
| `sources` | Array | Optional | Array of [URL source elements](https://docs.slack.dev/reference/block-kit/block-elements/url-source-element) used to generate a response. |
| `status` | String | Optional | The state of a task. **The accepted set depends on where the card sits:** `in_progress`, `complete` and `error` are accepted anywhere; `pending` is accepted only on a card nested in a plan's `tasks`, and is refused on a top-level `task_card`. Slack's table lists all four unconditionally. See "Status values depend on where the card sits" below. |
| `block_id` | String | Optional | A unique identifier for a block. If not specified, one will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |

### Usage info

A `task_card` block displays a single task which represents a single action. It includes a title, optional details and output (both as rich text), sources, and a status indicator.

### Status values depend on where the card sits

Slack documents one enum for `status` — `pending`, `in_progress`, `complete`, `error` — and says nothing about context. Two different sets are enforced:

| Where the card sits | Accepted values |
|---|---|
| A top-level `task_card` block | `in_progress`, `complete`, `error` |
| A task inside a `plan` block's `tasks` | `pending`, `in_progress`, `complete`, `error` |

`"status": "pending"` on a top-level `task_card` is refused with `invalid_blocks: must be a valid enum value`, even though it is documented as valid. The same card, moved into a plan's `tasks`, is accepted.

Also verified refused in both positions: `in-progress` with a hyphen, `done`, and `running`. The enum is closed and the separator is an underscore.

Everything above is measured against a live workspace. What follows is a reading of it, not a further measurement: "queued, not started" is a meaningful row of a plan, because the plan shows the rows that come after it, and is meaningless for a card standing on its own with nothing to be queued behind. That is inference. If a nested card ever needs a value that a standalone one refuses, trust the table above and not the reasoning.

**Slack's own example for this block is invalid as written.** It posts a top-level `task_card` with `"status": "pending"`, which is the combination that is refused. It is transcribed below unchanged, because it is the source's example; change the status or nest the card in a plan before posting it.

### `details` and `output` are the same panel

Both fields take a single [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) entity, and both render as the same body text under the task's title. The only observed difference is that `output` draws a leading dot at a slightly different indent.

There is no disclosure control, no expander, and no second panel: nothing is hidden behind a click, and neither field is labelled. Whatever Slack's naming suggests, they are not a "working notes" field and a "result" field with different behaviour.

Pick one. Setting both puts two paragraphs in the same place, which is only worth doing for that indent difference.

### Examples

```blockkit
{
  "blocks": [
    {
      "type": "task_card",
      "task_id": "task_1",
      "title": "Fetching weather data",
      "status": "pending",
      "output": {
        "type": "rich_text",
        "elements": [
          {
            "type": "rich_text_section",
            "elements": [
              {
                "type": "text",
                "text": "Found weather data for Chicago from 2 sources"
              }
            ]
          }
        ]
      },
      "sources": [
        {
          "type": "url",
          "url": "https://weather.com/",
          "text": "weather.com"
        },
        {
          "type": "url",
          "url": "https://www.accuweather.com/",
          "text": "accuweather.com"
        }
      ]
    }
  ]
}
```

As posted, that example fails: `"status": "pending"` is refused on a top-level `task_card`. Use `in_progress` here, or move the card into a `plan` block's `tasks`.


## Video block — `video`

Displays an embedded video player.

- **Surfaces:** Messages, Modals, Home tabs

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Required | The type of block. For a video block, type will always be `video`. |
| `alt_text` | string | Required | A tooltip for the video. Required for accessibility |
| `author_name` | string | Optional | Author name to be displayed. Must be less than 50 characters. |
| `block_id` | string | Optional | A unique identifier for a block. If not specified, one will be generated. Maximum length for this field is 255 characters. `block_id` should be unique for each message and each iteration of a message. If a message is updated, use a new `block_id`. |
| `description` | Object | Preferred | Description for video in the form of a [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) that must have `type` of `plain_text`. `text` within must be less than 200 characters. |
| `provider_icon_url` | string | Optional | Icon for the video provider, e.g. YouTube icon. |
| `provider_name` | string | Optional | The originating application or domain of the video, e.g. YouTube. |
| `title` | Object | Required | Video title in the form of a [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) that must have `type` of `plain_text`. `text` within must be less than 200 characters. |
| `title_url` | string | Preferred | Hyperlink for the title text. Must correspond to the non-embeddable URL for the video. Must go to an HTTPS URL. |
| `thumbnail_url` | string | Required | The thumbnail image URL |
| `video_url` | string | Required | The URL to be embedded. Must match any existing [unfurl domains](https://docs.slack.dev/messaging/unfurling-links-in-messages#configuring_domains) within the app and point to a HTTPS URL. |

### Usage info

A `video` block is designed to embed videos in all app surfaces (e.g. link unfurls, messages, modals, App Home) — anywhere you can put blocks! To use the video block within your app, you must have the [`links.embed:write`](https://docs.slack.dev/reference/scopes/links.embed.write) scope.

The metadata received in the block payload will be used to construct the description, provider, and title of the video in all clients. Developers have the flexibility to leave non-mandatory fields null and use other blocks to format this content.

### Requirements

- Video blocks can only be posted by apps; users are not allowed to post embedded videos directly from Block Kit Builder.
- Your app must have the the [`links.embed:write`](https://docs.slack.dev/reference/scopes/links.embed.write) scope for both user and bot tokens.
- `video_url` has to be included in the [unfurl domains](https://docs.slack.dev/messaging/unfurling-links-in-messages#configuring_domains) specified in your app.
- `video_url` should be publicly accessible, unless the app relies on information received from the [Events API](https://docs.slack.dev/apis/events-api/) payloads to make a decision on whether the viewer(s) of the content should have access. If so, the service could create a unique URL accessible only via Slack.
- `video_url` must be compatible with an embeddable iFrame.
- `video_url` must return a 2xx code OR 3xx with less than 5 redirects and an eventual 2xx.
- `video_url` must not point to any Slack-related domain.

### Constraints

- Embeddable video players only (audio-only permitted)
- Navigation, scrolling and overlays are not allowed within the iFrame.
- Interactivity (e.g. likes, comments, and reactions) are allowed within your player but shouldn't completely overlay or navigate away from the content being embedded. These interactions will be anonymous since no user data is transferred to the embedded view.

### Examples

```blockkit
{
  "blocks": [
    {
      "type": "video",
      "title": {
        "type": "plain_text",
        "text": "Use the Events API to create a dynamic App Home",
        "emoji": true
      },
      "title_url": "https://www.youtube.com/watch?v=8876OZV_Yy0",
      "description": {
        "type": "plain_text",
        "text": "Slack sure is nifty!",
        "emoji": true
      },
      "video_url": "https://www.youtube.com/embed/8876OZV_Yy0?feature=oembed&autoplay=1",
      "alt_text": "Use the Events API to create a dynamic App Home",
      "thumbnail_url": "https://i.ytimg.com/vi/8876OZV_Yy0/hqdefault.jpg"
    }
  ]
}
```
