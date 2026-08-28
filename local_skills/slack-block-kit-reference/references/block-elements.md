# Block elements

Elements are the interactive and inline components that live inside blocks. Each element names the blocks it may appear in; putting one in a block that does not accept it is rejected.

## Contents

- Attachment mention element — `attachment_mention`
- Broadcast element — `broadcast`
- Button element — `button`
- Canvas element — `canvas`
- Canvas message unfurl element — `canvas_message_unfurl`
- Canvas user mention element — `canvas_user_mention`
- Channel element — `channel`
- Checkboxes element — `checkboxes`
- Citation element — `citation`
- Color element — `color`
- Date element — `date`
- Date picker element — `datepicker`
- Datetime picker element — `datetimepicker`
- Email input element — `email_text_input`
- Emoji element — `emoji`
- Feedback buttons element — `feedback_buttons`
- File element — `file`
- File input element — `file_input`
- Icon button element — `icon_button`
- Image element — `image`
- Link element — `link`
- List record element — `list_record`
- Message mention element — `message_mention`
- Multi-select menu element — `multi_static_select` / `multi_external_select` / `multi_users_select` / `multi_conversations_select` / `multi_channels_select`
- Number input element — `number_input`
- Overflow menu element — `overflow`
- Plain-text input element — `plain_text_input`
- Radio button group element — `radio_buttons`
- Rich text input element — `rich_text_input`
- Rich text list element — `rich_text_list`
- Rich text preformatted element — `rich_text_preformatted`
- Rich text quote element — `rich_text_quote`
- Rich text section element — `rich_text_section`
- Salesforce data field element — `salesforce_data_field`
- Select menu element — `static_select` / `external_select` / `users_select` / `conversations_select` / `channels_select`
- Tag element — `tag`
- Team element — `team`
- Text element — `text`
- Time picker element — `timepicker`
- URL input element — `url_text_input`
- URL source element — `url`
- User element — `user`
- Usergroup element — `usergroup`
- Work object mention element — `work_object_mention`
- Workflow button element — `workflow_button`
- Workflow mention element — `workflow_mention`

---

## Attachment mention element — `attachment_mention`

Renders as a rich app attachment or entity reference.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "attachment_mention". |
| `url` | String | Required | The URL of the app attachment or entity to reference. |
| `text` | String | Optional | Fallback text if attachment not found. |
| `app_id` | String | Optional | The app ID that produced the unfurl. Used to fetch the app's profile for use in rendering. |
| `entity_id` | String | Optional | The Work Object entity ID when the attachment is a Work Object. |
| `icon_url` | String | Optional | An optional override of the icon URL. This will typically be used for adding the Work Object product icon, which can be different from the app's icon. |
| `channel_id` | String | Optional | The encoded channel ID where this attachment lives. |
| `ts` | String | Optional | The encoded message timestamp where this attachment lives. |
| `full_size_preview_enabled` | Boolean | Optional | Whether the work object supports full size preview. |
| `icon_name` | String | Optional | An optional icon name identifier for the attachment (e.g., sf-account, sf-record, sf-list for Salesforce attachments). |
| `reference_object_type` | String | Optional | An optional type identifier for the referenced object (e.g., list_view, record for Salesforce attachments). |
| `product_name` | String | Optional | The product name for the Work Object (e.g., Google Docs, Google Sheets). Used to determine per-product click behavior preferences when the attachment is not available. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "attachment_mention",
              "url": "https://example.com/attachment"
            }
          ]
        }
      ]
    }
  ]
}
```


## Broadcast element — `broadcast`

Displays a broadcast mention such as here, channel, or everyone.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "broadcast". |
| `range` | String | Required | The range of the broadcast; value can be `here`, `channel`, or `everyone`. Using `here` notifies only the active members of a channel; `channel` notifies all members of a channel; `everyone` notifies every person in the #general channel. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "broadcast",
              "range": "everyone"
            }
          ]
        }
      ]
    }
  ]
}
```


## Button element — `button`

Allows users a direct path to performing basic actions.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Section, Actions

Example:

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `button`. |
| `text` | Object | Required | A [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) that defines the button's text. Can only be of `type: plain_text`. `text` may truncate with ~30 characters. Maximum length for the `text` in this field is 75 characters. |
| `action_id` | String | Optional | An identifier for this action. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `url` | String | Optional | A URL to load in the user's browser when the button is clicked. Maximum length is 3000 characters. If you're using `url`, you'll still receive an [interaction payload](https://docs.slack.dev/interactivity/handling-user-interaction#payloads) and will need to [send an acknowledgement response](https://docs.slack.dev/interactivity/handling-user-interaction#acknowledgment_response). |
| `value` | String | Optional | The value to send along with the [interaction payload](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Maximum length is 2000 characters. |
| `style` | String | Optional | Decorates buttons with alternative visual color schemes. Use this option with restraint.`primary` gives buttons a green outline and text, ideal for affirmation or confirmation actions. `primary` should only be used for one button within a set.`danger` gives buttons a red outline and text, and should be used when the action is destructive. Use `danger` even more sparingly than `primary`.If you don't include this field, the default button style will be used. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog after the button is clicked. |
| `accessibility_label` | String | Optional | A label for longer descriptive text about a button element. This label will be read out by screen readers _instead of_ the button [`text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) object. Maximum length is 75 characters. |

### Examples

A regular interactive button:

```blockkit
{
  "type": "button",
  "text": {
    "type": "plain_text",
    "text": "Click Me"
  },
  "value": "click_me_123",
  "action_id": "button"
}
```

A button with a `primary` `style` attribute:

```blockkit
{
  "type": "button",
  "text": {
    "type": "plain_text",
    "text": "Save"
  },
  "style": "primary",
  "value": "click_me_123",
  "action_id": "button"
}
```

A link button:

```blockkit
{
  "type": "button",
  "text": {
    "type": "plain_text",
    "text": "Link Button"
  },
  "url": "https://docs.slack.dev/block-kit"
}
```

The button element must be used inside either the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) or [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block, like this:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "This is a section block with a button."
      },
      "accessory": {
        "type": "button",
        "text": {
          "type": "plain_text",
          "text": "Click Me"
        },
        "value": "click_me_123",
        "action_id": "button"
      }
    },
    {
      "type": "actions",
      "block_id": "actionblock789",
      "elements": [
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "Primary Button"
          },
          "style": "primary",
          "value": "click_me_456"
        },
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "Link Button"
          },
          "url": "https://api.slack.com/block-kit"
        }
      ]
    }
  ]
}
```


## Canvas element — `canvas`

Renders as a link to a canvas.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "canvas". |
| `file_id` | String | Required | The ID of the canvas to link to. |
| `label` | String | Optional | What the canvas is labeled. |
| `hide_title` | Boolean | Optional | Whether the title should be hidden. |
| `section_id` | String | Optional | The section ID. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |
| `text` | String | Optional | Title of the canvas. |
| `url` | String | Optional | URL of the canvas. |
| `is_skill_invocation` | Boolean | Optional | True when this canvas element was inserted as a skill invocation. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "canvas",
              "file_id": "F123ABC456"
            }
          ]
        }
      ]
    }
  ]
}
```


## Canvas message unfurl element — `canvas_message_unfurl`

Renders as an inline preview of a message inside a canvas.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "canvas_message_unfurl". |
| `root_message_ts` | String | Required | The timestamp of the root message. |
| `root_message_channel` | String | Required | The channel the root message was posted in. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, and `underline`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "canvas_message_unfurl",
              "root_message_ts": "1783613573",
              "root_message_channel": "CABCDEFGHI"
            }
          ]
        }
      ]
    }
  ]
}
```


## Canvas user mention element — `canvas_user_mention`

Renders as a user mention in canvas content.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "canvas_user_mention". |
| `user_id` | String | Required | The ID of the user to mention within canvas content. |
| `thread_id` | String | Optional | The ID of the thread. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "canvas_user_mention",
              "user_id": "U123ABC456"
            }
          ]
        }
      ]
    }
  ]
}
```


## Channel element — `channel`

Renders as a mention of a channel.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "channel". |
| `channel_id` | String | Required | The ID of the channel to be mentioned. |
| `tab_id` | String | Optional | The ID of a specific channel tab. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |
| `from_llm` | Boolean | Optional | Indicates whether the channel was generated by the LLM itself. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "channel",
              "channel_id": "C123ABC456"
            }
          ]
        }
      ]
    }
  ]
}
```


## Checkboxes element — `checkboxes`

Allows users to choose multiple items from a list of options.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Section, Actions, Input

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `checkboxes`. |
| `action_id` | String | Optional | An identifier for the action triggered when the checkbox group is changed. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `options` | Object[] | Required | An array of [option objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-object). A maximum of 10 options are allowed. |
| `initial_options` | Object[] | Optional | An array of [option objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-object) that exactly matches one or more of the options within `options`. These options will be selected when the checkbox group initially loads. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after clicking one of the checkboxes in this element. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |

### Example

The checkboxes element must be used inside the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block, [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block, or [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows a section block containing a group of checkboxes:

```blockkit
{
  "type": "modal",
  "title": {
    "type": "plain_text",
    "text": "My App",
    "emoji": true
  },
  "submit": {
    "type": "plain_text",
    "text": "Submit",
    "emoji": true
  },
  "close": {
    "type": "plain_text",
    "text": "Cancel",
    "emoji": true
  },
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "plain_text",
        "text": "Check out these charming checkboxes"
      },
      "accessory": {
        "type": "checkboxes",
        "action_id": "this_is_an_action_id",
        "initial_options": [
          {
            "value": "A1",
            "text": {
              "type": "plain_text",
              "text": "Checkbox 1"
            }
          }
        ],
        "options": [
          {
            "value": "A1",
            "text": {
              "type": "plain_text",
              "text": "Checkbox 1"
            }
          },
          {
            "value": "A2",
            "text": {
              "type": "plain_text",
              "text": "Checkbox 2"
            },
            "description": {
              "type": "mrkdwn",
              "text": "*A description of option two*"
            }
          }
        ]
      }
    }
  ]
}
```


## Citation element — `citation`

Renders as an AI citation (file, external, web, message, or memory).

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "citation". |
| `url` | String | Required | The URL of the cited source. |
| `text` | String | Required | The display text for the citation. |
| `index` | Number | Required | The index of the citation. |
| `details` | Object | Required | Details about the cited source. This can be a `file`, `external`, `web`, `message`, or `memory` object. See below for the schemas of each. |
| `from_llm` | Boolean | Optional | Indicates whether the citation was generated by the LLM itself. |
| `is_slack_url` | Boolean | Optional | Indicates whether the citation is a Slack URL. |

The following schemas are the options for the `details` object.

The `file` object:

```blockkit
{
  "citation_type": {
    "type": "string",
    "enum": "file"
  },
  "descriptor": {
    "type": "string"
  },
  "file_id": {
    "type": "string"
  }
}
```

The `external` object:

```blockkit
{
  "citation_type": {
    "type": "string",
    "enum": "external"
  },
  "app_name": {
    "type": "string"
  },
  "app_icon_url": {
    "type": "string"
  }
}
```

The `web` object:

```blockkit
{
  "citation_type": {
    "type": "string",
    "enum": "web"
  },
  "display_name": {
    "type": "string"
  },
  "title": {
    "type": "string"
  },
  "snippet": {
    "type": "string"
  }
}
```

The `message` object:

```blockkit
{
  "citation_type": {
    "type": "string",
    "enum": "message"
  },
  "channel": {
    "type": "string"
  },
  "message_ts": {
    "type": "string"
  }
}
```

The `memory` object:

```blockkit
{
  "citation_type": {
    "type": "string",
    "enum": "memory"
  },
  "memory_id": {
    "type": "string"
  }
}
```

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "citation",
              "url": "https://example.com/source",
              "text": "Source title",
              "index": 1,
              "details": {
                "citation_type": "file",
                "descriptor": "Team canvas",
                "file_id": "F0ABCDEFG12"
              }
            }
          ]
        }
      ]
    }
  ]
}
```


## Color element — `color`

Displays a color swatch from a hex value.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "color". |
| `value` | String | Required | The hex value for the color. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, and `underline`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "color",
              "value": "#F405B3"
            }
          ]
        }
      ]
    }
  ]
}
```


## Date element — `date`

Displays a formatted, localized date.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case "date". |
| `timestamp` | Number | Required | A Unix timestamp for the date to be displayed in seconds. |
| `format` | String | Required | A template string containing curly-brace-enclosed tokens to substitute your provided `timestamp`. See details below. |
| `timezone` | String | Optional | The timezone in which the date is in. |
| `url` | String | Optional | URL to link the entire `format` string to. |
| `fallback` | String | Optional | Text to display in place of the date should parsing, formatting or displaying fail. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, and `underline`. |

### Date format strings

The following are the template strings allowed by the `format` property of the `date` element type.

- `{day_divider_pretty}`: Shows `today`, `yesterday` or `tomorrow` if applicable. Otherwise, if the date is in current year, uses the `{date_long}` format without the year. Otherwise, falls back to using the `{date_long}` format.
- `{date_num}`: Shows date as YYYY-MM-DD.
- `{date_slash}`: Shows date as DD/MM/YYYY (subject to locale preferences).
- `{date_long}`: Shows date as a long-form sentence including day-of-week, e.g. `Monday, December 23rd, 2013`.
- `{date_long_full}`: Shows date as a long-form sentence without day-of-week, e.g. `August 9, 2020`.
- `{date_long_pretty}`: Shows `yesterday`, `today` or `tomorrow`, otherwise uses the `{date_long}` format.
- `{date}`: Same as `{date_long_full}` but without the year.
- `{date_pretty}`: Shows `today`, `yesterday` or `tomorrow` if applicable, otherwise uses the `{date}` format.
- `{date_short}`: Shows date using short month names without day-of-week, e.g. `Aug 9, 2020`.
- `{date_short_pretty}`: Shows `today`, `yesterday` or `tomorrow` if applicable, otherwise uses the `{date_short}` format.
- `{time}`: Depending on user preferences, shows just the time-of-day portion of the timestamp using either 12 or 24 hour clock formats, e.g. `2:34 PM` or `14:34`.
- `{time_secs}`: Depending on user preferences, shows just the time-of-day portion of the timestamp using either 12 or 24 hour clock formats, including seconds, e.g. `2:34:56 PM` or `14:34:56`.
- `{ago}`: A human-readable period of time, e.g. `3 minutes ago`, `4 hours ago`, `2 days ago`.

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "date",
              "timestamp": 1720710212,
              "format": "{date_num} at {time}",
              "fallback": "timey"
            }
          ]
        }
      ]
    }
  ]
}
```


## Date picker element — `datepicker`

Allows users to select a date from a calendar style UI.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Section, Actions, Input

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `datepicker`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_date` | String | Optional | The initial date that is selected when the element is loaded. This should be in the format `YYYY-MM-DD`. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after a date is selected. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the datepicker. Maximum length for the `text` in this field is 150 characters. |

### Example

The date picker element must be used inside the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block, [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block, or [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows a section block containing a date picker element:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section1234",
      "text": {
        "type": "mrkdwn",
        "text": "Pick a date for the deadline."
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


## Datetime picker element — `datetimepicker`

Allows users to select both a date and a time of day.

- **Surfaces:** Messages, Modals
- **Works with blocks:** Actions, Input

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `datetimepicker`. |
| `action_id` | String | Optional | An identifier for the input value when the parent modal is submitted. You can use this when you receive a `view_submission` payload [to identify the value of the input element](https://docs.slack.dev/surfaces/modals#interactions). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_date_time` | Integer | Optional | The initial date and time that is selected when the element is loaded, represented as a UNIX timestamp in seconds. This should be in the format of 10 digits, for example `1628633820` represents the date and time August 10th, 2021 at 03:17pm PST. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after a time is selected. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |

### Usage Info

_Interactive component_ - see our [guide to enabling interactivity](https://docs.slack.dev/interactivity/handling-user-interaction).

On desktop clients, the time picker will take the form of a dropdown list and the date picker will take the form of a dropdown calendar. Both options will have free-text entry for precise choices. On mobile clients, the time picker and date picker will use native UIs.

### Example

The datetime picker element must be used inside the [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block or [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows an input block containing a datetime picker element:

```blockkit
{
  "blocks": [
    {
      "type": "input",
      "element": {
        "type": "datetimepicker",
        "action_id": "datetimepicker-action"
      },
      "hint": {
        "type": "plain_text",
        "text": "This is some hint text",
        "emoji": true
      },
      "label": {
        "type": "plain_text",
        "text": "Start date",
        "emoji": true
      }
    }
  ]
}
```


## Email input element — `email_text_input`

Allows user to enter an email into a single-line field.

- **Surfaces:** Modals
- **Works with blocks:** Input

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `email_text_input`. |
| `action_id` | String | Optional | An identifier for the input value when the parent modal is submitted. You can use this when you receive a `view_submission` payload [to identify the value of the input element](https://docs.slack.dev/surfaces/modals#interactions). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_value` | String | Optional | The initial value in the email input when it is loaded. |
| `dispatch_action_config` | Object | Optional | A [dispatch configuration object](https://docs.slack.dev/reference/block-kit/composition-objects/dispatch-action-configuration-object) that determines when during text input the element returns a [`block_actions` payload](https://docs.slack.dev/reference/interaction-payloads/block_actions-payload). |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown in the email input. Maximum length for the `text` in this field is 150 characters. |

### Example

The email input element must be used inside the [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows an input block containing an email input element.

```blockkit
{
  "blocks": [
    {
      "type": "input",
      "block_id": "input123",
      "label": {
        "type": "plain_text",
        "text": "Email Address"
      },
      "element": {
        "type": "email_text_input",
        "action_id": "email_text_input-action",
        "placeholder": {
          "type": "plain_text",
          "text": "Enter an email"
        }
      }
    }
  ]
}
```


## Emoji element — `emoji`

Displays an emoji.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "emoji". |
| `name` | String | Required | The name of the emoji; i.e. "wave" or "wave::skin-tone-2". The bare name, with no surrounding colons. |
| `unicode` | String | Optional | Represents the unicode code point of the emoji, where applicable. |

### This is the only way to put an emoji in rich text

A `:shortcode:` written into a [`text` element](https://docs.slack.dev/reference/block-kit/block-elements/text-element)'s `text` is not parsed — it renders as the literal colons and letters. That is true even though the same shortcode in a `section` block's `mrkdwn` text object does render an emoji. Verified against a live workspace.

So an emoji in a `rich_text` block is an `emoji` element sitting alongside the `text` elements, exactly as in the example below. `name` carries the shortcode without its colons: `{"type": "emoji", "name": "white_check_mark"}`, never `":white_check_mark:"`.

A literal unicode emoji character inside a `text` element does render, and is a workable fallback. Prefer the element: it names the emoji semantically and does not depend on the source encoding.

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "emoji",
              "name": "basketball"
            },
            {
              "type": "text",
              "text": " "
            },
            {
              "type": "emoji",
              "name": "snowboarder"
            },
            {
              "type": "text",
              "text": " "
            },
            {
              "type": "emoji",
              "name": "checkered_flag"
            }
          ]
        }
      ]
    }
  ]
}
```


## Feedback buttons element — `feedback_buttons`

Buttons to indicate positive or negative feedback.

- **Surfaces:** Messages
- **Works with blocks:** Context actions

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `feedback_buttons`. |
| `positive_button` | Object | Required | A button to indicate positive feedback. See button object fields below. |
| `negative_button` | Object | Required | A button to indicate negative feedback. See button object fields below. |
| `action_id` | String | Optional | An identifier for this action. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id` values in the containing block. Maximum length is 255 characters. |

### Button object fields

Both `positive_button` and `negative_button` contain the following fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | Object | Required | A [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) that defines the button's text. Can only be of `type: plain_text`. Maximum length for the `text` in this field is 75 characters. |
| `value` | String | Required | The value to send along with the [interaction payload](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Maximum length is 2000 characters. |
| `accessibility_label` | String | Optional | A label for longer descriptive text about a button element. This label will be read out by screen readers instead of the button `text` object. Maximum length is 75 characters. |

### Example

The feedback buttons element must be used inside the [context actions](https://docs.slack.dev/reference/block-kit/blocks/context-actions-block) block, like this:

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
              "text": "Good"
            },
            "value": "positive_feedback",
            "accessibility_label": "Mark this response as good"
          },
          "negative_button": {
            "text": {
              "type": "plain_text",
              "text": "Bad"
            },
            "value": "negative_feedback",
            "accessibility_label": "Mark this response as bad"
          }
        }
      ]
    }
  ]
}
```

[Preview in Block Kit Builder](https://app.slack.com/block-kit-builder/T024BE7LD#%7B%22blocks%22:%5B%7B%22type%22:%22context_actions%22,%22elements%22:%5B%7B%22type%22:%22feedback_buttons%22,%22action_id%22:%22feedback_buttons_1%22,%22positive_button%22:%7B%22text%22:%7B%22type%22:%22plain_text%22,%22text%22:%22%F0%9F%91%8D%22%7D,%22value%22:%22positive_feedback%22%7D,%22negative_button%22:%7B%22text%22:%7B%22type%22:%22plain_text%22,%22text%22:%22%F0%9F%91%8E%22%7D,%22value%22:%22negative_feedback%22%7D%7D%5D%7D%5D%7D)


## File element — `file`

Renders as a link to a Slack file.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "file". |
| `file_id` | String | Required | The ID of the file to link to. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, and `underline`. |
| `text` | String | Optional | Title of the file. |
| `url` | String | Optional | URL of the file. |
| `is_skill_invocation` | Boolean | Optional | Indicates whether this file element was inserted as a skill invocation. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "file",
              "file_id": "F123ABC456"
            }
          ]
        }
      ]
    }
  ]
}
```


## File input element — `file_input`

Allows user to upload files.

- **Surfaces:** Modals
- **Works with blocks:** Input

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `file_input`. |
| `action_id` | String | Optional | An identifier for the input value when the parent modal is submitted. You can use this when you receive a `view_submission` payload [to identify the value of the input element](https://docs.slack.dev/surfaces/modals#interactions). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `filetypes` | String[] | Optional | An array of valid [file extensions](https://docs.slack.dev/reference/objects/file-object#types) that will be accepted for this element. All file extensions will be accepted if filetypes is not specified. This validation is provided for convenience only, and you should perform your own file type validation based on what you expect to receive. |
| `max_files` | Integer | Optional | Maximum number of files that can be uploaded for this `file_input` element. Minimum of 1, maximum of 10. Defaults to 10 if not specified. |

### Usage info

In order to use the `file_input` element within your app, your app must have the [`files:read`](https://docs.slack.dev/reference/scopes/files.read) scope. There is a 100MB file size limit.

### Example

The file input element must be used inside the [input block](https://docs.slack.dev/reference/block-kit/blocks/input-block) block, like this:

```blockkit
{
  "title": {
    "type": "plain_text",
    "text": "My App",
    "emoji": true
  },
  "submit": {
    "type": "plain_text",
    "text": "Submit",
    "emoji": true
  },
  "type": "modal",
  "close": {
    "type": "plain_text",
    "text": "Cancel",
    "emoji": true
  },
  "blocks": [
    {
      "type": "input",
      "block_id": "input_block_id",
      "label": {
        "type": "plain_text",
        "text": "Upload Files"
      },
      "element": {
        "type": "file_input",
        "action_id": "file_input_action_id_1",
        "filetypes": [
          "jpg",
          "png"
        ],
        "max_files": 5
      }
    }
  ]
}
```


## Icon button element — `icon_button`

An icon button to perform actions.

- **Surfaces:** Messages
- **Works with blocks:** Context actions

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `icon_button`. |
| `icon` | String | Required | The icon to show. The `trash` icon is the only icon available at this time. |
| `text` | Object | Required | A [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) that defines the button's text. Can only be of `type: plain_text`. |
| `action_id` | String | Optional | An identifier for this action. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `value` | String | Optional | The value to send along with the [interaction payload](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Maximum length is 2000 characters. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog after the button is clicked. |
| `accessibility_label` | String | Optional | A label for longer descriptive text about a button element. This label will be read out by screen readers instead of the button `text` object. Maximum length is 75 characters. |
| `visible_to_user_ids` | Array | Optional | An array of user IDs for which the icon button appears. If not provided, the button is visible to all users. |

### Examples

The icon button must be used inside of the [context actions](https://docs.slack.dev/reference/block-kit/blocks/context-actions-block) block, like this:

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
          "action_id": "delete_button",
          "value": "delete_item"
        }
      ]
    }
  ]
}
```

[Preview in Block Kit Builder](https://app.slack.com/block-kit-builder/T024BE7LD#%7B%22blocks%22:%5B%7B%22type%22:%22context_actions%22,%22elements%22:%5B%7B%22type%22:%22icon_button%22,%22icon%22:%22trash%22,%22text%22:%7B%22type%22:%22plain_text%22,%22text%22:%22Delete%22%7D,%22action_id%22:%22delete_button%22,%22value%22:%22delete_item%22%7D%5D%7D%5D%7D)


## Image element — `image`

Displays an image as part of a larger block of content.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Section, Context

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `image`. |
| `alt_text` | String | Required | A plain-text summary of the image. This should not contain any markup. |
| `image_url` | String | Optional | The URL for a publicly hosted image. You must provide either an `image_url` or `slack_file`. Maximum length for this field is 3000 characters. |
| `slack_file` | Object | Optional | A [Slack image file object](https://docs.slack.dev/reference/block-kit/composition-objects/slack-file-object) that defines the source of the image. |

### Usage info

Use the [`image`](https://docs.slack.dev/reference/block-kit/blocks/image-block) block if you want a block with _only_ an image in it.

### Examples

The image element must be used inside of the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block or the [context](https://docs.slack.dev/reference/block-kit/blocks/context-block) block.

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section567",
      "text": {
        "type": "mrkdwn",
        "text": "This is a section block with an accessory image."
      },
      "accessory": {
        "type": "image",
        "image_url": "https://pbs.twimg.com/profile_images/625633822235693056/lNGUneLX_400x400.jpg",
        "alt_text": "cute cat"
      }
    }
  ]
}
```

An image block using `slack_file` with a `url`:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section567",
      "text": {
        "type": "mrkdwn",
        "text": "This is a section block with an accessory image."
      },
      "accessory": {
        "type": "image",
        "slack_file": {
          "url": "https://files.slack.com/files-pri/T0123456-F0123456/xyz.png"
        },
        "alt_text": "Slack file object."
      }
    }
  ]
}
```

An image block using `slack_file` with a `id`:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section567",
      "text": {
        "type": "mrkdwn",
        "text": "This is a section block with an accessory image."
      },
      "accessory": {
        "type": "image",
        "slack_file": {
          "id": "F01234567"
        },
        "alt_text": "Slack file object."
      }
    }
  ]
}
```


## Link element — `link`

Displays a hyperlink.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case "link". |
| `url` | String | Required | The link's url. |
| `text` | String | Optional | The text shown to the user (instead of the url). If no text is provided, the url is used. |
| `unsafe` | Boolean | Optional | Indicates whether the link is safe. |
| `from_llm` | Boolean | Optional | Indicates whether the link was generated by the LLM itself. |
| `is_slack_url` | Boolean | Optional | Indicates whether the link is a Slack URL. |
| `truncated` | Boolean | Optional | Indicates whether the link has been truncated. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "link",
              "url": "https://docs.slack.dev"
            }
          ]
        }
      ]
    }
  ]
}
```


## List record element — `list_record`

Renders as a link to a Slack list record.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "list_record". |
| `file_id` | String | Required | The ID of the Slack list record to link to. |
| `record_id` | String | Optional | The record ID. |
| `view_id` | String | Optional | View ID of the list record. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |
| `text` | String | Optional | Title of the list record. |
| `url` | String | Optional | URL of the list record. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "list_record",
              "file_id": "F123ABC456"
            }
          ]
        }
      ]
    }
  ]
}
```


## Message mention element — `message_mention`

Renders as a link to a Slack message.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "message_mention". |
| `channel_id` | String | Required | The ID of the channel containing the message. |
| `message_ts` | String | Required | The timestamp of the message to link to. |
| `author_id` | String | Optional | ID of the author of the message. |
| `thread_ts` | String | Optional | Timestamp of when the message mention occurred. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |
| `text` | String | Optional | Text representing the message. |
| `url` | String | Optional | URL of the message. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "message_mention",
              "channel_id": "C123ABC456",
              "message_ts": "1720710212.123456"
            }
          ]
        }
      ]
    }
  ]
}
```


## Multi-select menu element — `multi_static_select` / `multi_external_select` / `multi_users_select` / `multi_conversations_select` / `multi_channels_select`

Allows users to select multiple items from a list of options.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Section, Actions, Input

### Usage info

_Interactive component_ - see our [guide to enabling interactivity](https://docs.slack.dev/interactivity/handling-user-interaction).

Just like regular [select menus](https://docs.slack.dev/reference/block-kit/block-elements/select-menu-element), multi-select menus also include type-ahead functionality, where a user can type a part or all of an option string to filter the list.

There are different types of multi-select menu that depend on different data sources for their lists of options:

- Menu with static options
- Menu with external data source
- Menu with user list
- Menu with conversations list
- Menu with channels list

Example:

### Static options

This is the most basic form of select menu, with a static list of options passed in when defining the element.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `multi_static_select`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/messaging/creating-interactive-messages#understanding_payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `options` | Object[] | Required | An array of [option objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-object). Maximum number of options is 100. Each option must be less than 76 characters. If `option_groups` is specified, this field should not be. |
| `option_groups` | Object[] | Optional | An array of [option group objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-group-object). Maximum number of option groups is 100. If `options` is specified, this field should not be. |
| `initial_options` | Object[] | Optional | An array of [option objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-object) that exactly match one or more of the options within `options` or `option_groups`. These options will be selected when the menu initially loads. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears before the multi-select choices are submitted. |
| `max_selected_items` | Integer | Optional | Specifies the maximum number of items that can be selected in the menu. Minimum number is 1. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text` only text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) that defines the placeholder text shown on the menu. Maximum length for the `text` in this field is 150 characters. |

### Example

The multi-select menu element must be used inside of the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block, [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block, or [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows a section block containing a static multi-select menu:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section678",
      "text": {
        "type": "mrkdwn",
        "text": "Pick items from the list"
      },
      "accessory": {
        "action_id": "text1234",
        "type": "multi_static_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select items"
        },
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
          }
        ]
      }
    }
  ]
}
```

### External data source

This menu will load its options from an external data source, allowing for a dynamic list of options.

### Setup

To use this menu type, you'll need to configure your app first:

1.  Go to your [app's settings page](https://api.slack.com/apps) and select **Interactivity & Shortcuts** from the sidebar.
2.  Add a URL to the **Options Load URL** under Select Menus.
3.  Save changes.

Each time a menu of this type is opened or the user starts typing in the typeahead field, we'll send a request to your specified URL. Your app should return an HTTP 200 OK response, along with an `application/json` post body with an object containing either:

- an [`options`](https://docs.slack.dev/reference/block-kit/composition-objects/option-object) array
- an [`option_groups`](https://docs.slack.dev/reference/block-kit/composition-objects/option-group-object) array

The `option_groups` array can have a maximum number of 100 option groups with a maximum of 100 options.

Here's an example response:

```blockkit
{
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
    }
  ]
}
```

### Making the element optional

By default, external multi-select menu elements require a user to select at least one option from the drop-down menu. However, there is a way to make a selection from this element optional. This is done by containing the element within an [input block](https://docs.slack.dev/reference/block-kit/blocks/input-block), and using its `optional` field to designate the input element as an optional element. (In fact, any Block Kit element can be made optional this way!)

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `multi_external_select`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `min_query_length` | Integer | Optional | When the typeahead field is used, a request will be sent on every character change. If you prefer fewer requests or more fully ideated queries, use the `min_query_length` attribute to tell Slack the fewest number of typed characters required before dispatch. The default value is `3`. |
| `initial_options` | Object[] | Optional | An array of [option objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-object) that exactly match one or more of the options within `options` or `option_groups`. These options will be selected when the menu initially loads. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears before the multi-select choices are submitted. |
| `max_selected_items` | Integer | Optional | Specifies the maximum number of items that can be selected in the menu. Minimum number is 1. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the menu. Maximum length for the `text` in this field is 150 characters. |

### Example

A multi-select menu in a section block with an external data source:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section678",
      "text": {
        "type": "mrkdwn",
        "text": "Pick items from the list"
      },
      "accessory": {
        "action_id": "text1234",
        "type": "multi_external_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select items"
        },
        "min_query_length": 3
      }
    }
  ]
}
```

### User list

This multi-select menu will populate its options with a list of Slack users visible to the current user in the active workspace.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `multi_users_select`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_users` | String[] | Optional | An array of user IDs of any valid users to be pre-selected when the menu loads. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears before the multi-select choices are submitted. |
| `max_selected_items` | Integer | Optional | Specifies the maximum number of items that can be selected in the menu. Minimum number is 1. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the menu. Maximum length for the `text` in this field is 150 characters. |

### Example

A multi-select menu in a section block showing a list of users:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section678",
      "text": {
        "type": "mrkdwn",
        "text": "Pick users from the list"
      },
      "accessory": {
        "action_id": "text1234",
        "type": "multi_users_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select users"
        }
      }
    }
  ]
}
```

### Conversations list

This multi-select menu will populate its options with a list of public and private channels, DMs, and MPIMs visible to the current user in the active workspace.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `multi_conversations_select`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_conversations` | String[] | Optional | An array of one or more IDs of any valid conversations to be pre-selected when the menu loads. If `default_to_current_conversation` is also supplied, `initial_conversations` will be ignored. |
| `default_to_current_conversation` | Boolean | Optional | Pre-populates the select menu with the conversation that the user was viewing when they opened the modal, if available. Default is `false`. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears before the multi-select choices are submitted. |
| `max_selected_items` | Integer | Optional | Specifies the maximum number of items that can be selected in the menu. Minimum number is 1. |
| `filter` | Object | Optional | A [filter object](https://docs.slack.dev/reference/block-kit/composition-objects/conversation-filter-object) that reduces the list of available conversations using the specified criteria. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the menu. Maximum length for the `text` in this field is 150 characters. |

### Example

A multi-select menu in a section block showing a list of conversations:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section678",
      "text": {
        "type": "mrkdwn",
        "text": "Pick conversations from the list"
      },
      "accessory": {
        "action_id": "text1234",
        "type": "multi_conversations_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select conversations"
        }
      }
    }
  ]
}
```

### Public channels select

This multi-select menu will populate its options with a list of public channels visible to the current user in the active workspace.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `multi_channels_select`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_channels` | String[] | Optional | An array of one or more IDs of any valid public channel to be pre-selected when the menu loads. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears before the multi-select choices are submitted. |
| `max_selected_items` | Integer | Optional | Specifies the maximum number of items that can be selected in the menu. Minimum number is 1. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the menu. Maximum length for the `text` in this field is 150 characters. |

### Example

A multi-select menu in a section block showing a list of channels:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section678",
      "text": {
        "type": "mrkdwn",
        "text": "Pick channels from the list"
      },
      "accessory": {
        "action_id": "text1234",
        "type": "multi_channels_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select channels"
        }
      }
    }
  ]
}
```


## Number input element — `number_input`

Allows user to enter a number into a single-line field.

- **Surfaces:** Modals
- **Works with blocks:** Input

Example:

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `number_input`. |
| `is_decimal_allowed` | Boolean | Required | Decimal numbers are allowed if `is_decimal_allowed`\= `true`, set the value to `false` otherwise. |
| `action_id` | String | Optional | An identifier for the input value when the parent modal is submitted. You can use this when you receive a `view_submission` payload [to identify the value of the input element](https://docs.slack.dev/surfaces/modals#interactions). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_value` | String | Optional | The initial value in the plain-text input when it is loaded. |
| `min_value` | String | Optional | The minimum value, cannot be greater than `max_value`. |
| `max_value` | String | Optional | The maximum value, cannot be less than `min_value`. |
| `dispatch_action_config` | Object | Optional | A [dispatch configuration object](https://docs.slack.dev/reference/block-kit/composition-objects/dispatch-action-configuration-object) that determines when during text input the element returns a [`block_actions` payload](https://docs.slack.dev/reference/interaction-payloads/block_actions-payload). |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown in the number input. Maximum length for the `text` in this field is 150 characters. |

### Usage info

_Interactive component_ - see our [guide to enabling interactivity](https://docs.slack.dev/interactivity/handling-user-interaction).

The number input element accepts both whole and decimal numbers. For example, 0.25, 5.5, and -10 are all valid input values. Decimal numbers are only allowed when `is_decimal_allowed` is equal to `true`.

### Example

The number input element must be used inside of the [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block, like this:

```blockkit
{
  "blocks": [
    {
      "type": "input",
      "element": {
        "type": "number_input",
        "is_decimal_allowed": false,
        "action_id": "number_input-action"
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

[Preview in Block Kit Builder](https://app.slack.com/block-kit-builder/T024BE7LD#%7B%22blocks%22:%5B%7B%22type%22:%22input%22,%22element%22:%7B%22type%22:%22number_input%22,%22is_decimal_allowed%22:false,%22action_id%22:%22number_input-action%22%7D,%22label%22:%7B%22type%22:%22plain_text%22,%22text%22:%22Label%22,%22emoji%22:true%7D%7D%5D%7D)


## Overflow menu element — `overflow`

Allows users to press a button to view a list of options.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Section, Actions

### Usage info

_Interactive component_ - see our [guide to enabling interactivity](https://docs.slack.dev/interactivity/handling-user-interaction).

Unlike the select menu, there is no typeahead field, and the button always appears with an ellipsis ("…") rather than customizable text. As such, it is usually used if you want a more compact layout than a select menu, or to supply a list of less visually important actions after a row of buttons. You can also specify URL links as overflow menu options, instead of actions.

Example:

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `overflow`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `options` | Object[] | Required | An array of up to five [option objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-object) to display in the menu. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after a menu item is selected. |

### Example

The overflow menu element must be used inside of the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block or [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block. This example shows a section block containing an overflow menu:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section 890",
      "text": {
        "type": "mrkdwn",
        "text": "This is a section block with an overflow menu."
      },
      "accessory": {
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
      }
    }
  ]
}
```


## Plain-text input element — `plain_text_input`

Allows users to enter freeform text data into a single-line or multi-line field.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Input

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `plain_text_input`. |
| `action_id` | String | Optional | An identifier for the input value when the parent modal is submitted. You can use this when you receive a `view_submission` payload [to identify the value of the input element](https://docs.slack.dev/surfaces/modals#interactions). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_value` | String | Optional | The initial value in the plain-text input when it is loaded. |
| `multiline` | Boolean | Optional | Indicates whether the input will be a single line (`false`) or a larger textarea (`true`). Defaults to `false`. |
| `min_length` | Integer | Optional | The minimum length of input that the user must provide. If the user provides less, they will receive an error. Acceptable values for this field are between 0 and 3000, inclusive. |
| `max_length` | Integer | Optional | The maximum length of input that the user can provide. If the user provides more, they will receive an error. Acceptable values for this field are between 1 and 3000, inclusive. |
| `dispatch_action_config` | Object | Optional | A [dispatch configuration object](https://docs.slack.dev/reference/block-kit/composition-objects/dispatch-action-configuration-object) that determines when during text input the element returns a [`block_actions` payload](https://docs.slack.dev/reference/interaction-payloads/block_actions-payload). |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown in the plain-text input. Maximum length for the `text` in this field is 150 characters. |

### Example

The plain-text element must be used inside of the [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows an input block containing a plain-text input element.

```blockkit
{
  "blocks": [
    {
      "type": "input",
      "element": {
        "type": "plain_text_input",
        "action_id": "plain_text_input-action"
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


## Radio button group element — `radio_buttons`

Allows users to choose one item from a list of possible options.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Section, Actions, Input

Example:

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `radio_buttons`. |
| `action_id` | String | Optional | An identifier for the action triggered when the radio button group is changed. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `options` | Object[] | Required | An array of [option objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-object). A maximum of 10 options are allowed. |
| `initial_option` | Object | Optional | An [option object](https://docs.slack.dev/reference/block-kit/composition-objects/option-object) that exactly matches one of the options within `options`. This option will be selected when the radio button group initially loads. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after clicking one of the radio buttons in this element. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |

### Example

The radio button group element must be used inside of the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block, [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block, or [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows a section block containing a set of radio buttons:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "plain_text",
        "text": "Check out these rad radio buttons"
      },
      "accessory": {
        "type": "radio_buttons",
        "action_id": "this_is_an_action_id",
        "initial_option": {
          "value": "A1",
          "text": {
            "type": "plain_text",
            "text": "Radio 1"
          }
        },
        "options": [
          {
            "value": "A1",
            "text": {
              "type": "plain_text",
              "text": "Radio 1"
            }
          },
          {
            "value": "A2",
            "text": {
              "type": "plain_text",
              "text": "Radio 2"
            }
          }
        ]
      }
    }
  ]
}
```


## Rich text input element — `rich_text_input`

Allows users to enter formatted text in a WYSIWYG composer, offering the same messaging writing experience as in Slack.

- **Surfaces:** Modals, Home tabs
- **Works with blocks:** Input, Table

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `rich_text_input`. |
| `action_id` | String | Required | An identifier for the input value when the parent modal is submitted. You can use this when you receive a `view_submission` payload [to identify the value of the input element](https://docs.slack.dev/surfaces/modals#interactions). Should be unique in the containing block. Maximum length is 255 characters. |
| `initial_value` | [Rich text](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) | Optional | The initial value in the rich text input when it is loaded. |
| `dispatch_action_config` | Object | Optional | A [dispatch configuration object](https://docs.slack.dev/reference/block-kit/composition-objects/dispatch-action-configuration-object) that determines when during text input the element returns a [`block_actions`](https://docs.slack.dev/reference/interaction-payloads/block_actions-payload) payload. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) object that defines the placeholder text shown in the plain-text input. Maximum length for the `text` in this field is 150 characters. |
| `min_lines` | Integer | Optional | The minimum number of visible text lines the input should display before scrolling. Controls the initial height of the input. Must be between 1 and 100. |
| `max_lines` | Integer | Optional | The maximum number of visible text lines the input can grow to before scrolling. Defaults to 8 when omitted. Must be between 1 and 100. |

### Example

The rich text input element must be used inside of the [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows an input block containing a rich text input element.

```blockkit
{
  "blocks": [
    {
      "type": "input",
      "element": {
        "type": "rich_text_input",
        "action_id": "rich_text_input-action",
        "dispatch_action_config": {
          "trigger_actions_on": [
            "on_character_entered"
          ]
        },
        "focus_on_load": true,
        "placeholder": {
          "type": "plain_text",
          "text": "Enter text"
        }
      },
      "label": {
        "type": "plain_text",
        "text": "Label",
        "emoji": true
      }
    }
  ],
  "type": "home"
}
```


## Rich text list element — `rich_text_list`

Displays a list of rich text items.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of sub-element; in this case, `rich_text_list`. |
| `style` | String | Required | Either `bullet` or `ordered`, the latter meaning a numbered list. |
| `elements` | Object [] | Required | An array of [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) objects containing two properties: `type`, which is "rich_text_section", and `elements`, which is an array of rich text elements. Rich text elements include [`attachment_mention`](https://docs.slack.dev/reference/block-kit/block-elements/attachment-mention-element), [`broadcast`](https://docs.slack.dev/reference/block-kit/block-elements/broadcast-element), [`canvas`](https://docs.slack.dev/reference/block-kit/block-elements/canvas-element), [`canvas_user_mention`](https://docs.slack.dev/reference/block-kit/block-elements/canvas-user-mention-element), [`canvas_message_unfurl`](https://docs.slack.dev/reference/block-kit/block-elements/canvas-message-unfurl-element), [`channel`](https://docs.slack.dev/reference/block-kit/block-elements/channel-element), [`citation`](https://docs.slack.dev/reference/block-kit/block-elements/citation-element), [`color`](https://docs.slack.dev/reference/block-kit/block-elements/color-element), [`date`](https://docs.slack.dev/reference/block-kit/block-elements/date-element), [`emoji`](https://docs.slack.dev/reference/block-kit/block-elements/emoji-element), [`file`](https://docs.slack.dev/reference/block-kit/block-elements/file-element), [`link`](https://docs.slack.dev/reference/block-kit/block-elements/link-element), [`list_record`](https://docs.slack.dev/reference/block-kit/block-elements/list-record-element), [`message_mention`](https://docs.slack.dev/reference/block-kit/block-elements/message-mention-element), [`salesforce_data_field`](https://docs.slack.dev/reference/block-kit/block-elements/salesforce-data-field-element), [`tag`](https://docs.slack.dev/reference/block-kit/block-elements/tag-element), [`team`](https://docs.slack.dev/reference/block-kit/block-elements/team-element), [`text`](https://docs.slack.dev/reference/block-kit/block-elements/text-element), [`user`](https://docs.slack.dev/reference/block-kit/block-elements/user-element), [`usergroup`](https://docs.slack.dev/reference/block-kit/block-elements/usergroup-element), [`work_object_mention`](https://docs.slack.dev/reference/block-kit/block-elements/work-object-mention-element), [`workflow_mention`](https://docs.slack.dev/reference/block-kit/block-elements/workflow-mention-element). |
| `indent` | Number | Optional | Sub-list indent level. |
| `offset` | Number | Optional | Number to offset the first number in the list. For example, if the `offset = 4`, the first number in the ordered list would be 5. |
| `border` | Number | Optional | Turn the border on or off. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "block_id": "block1",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "text",
              "text": "My favorite Slack features (in no particular order):"
            }
          ]
        },
        {
          "type": "rich_text_list",
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [
                {
                  "type": "text",
                  "text": "Huddles"
                }
              ]
            },
            {
              "type": "rich_text_section",
              "elements": [
                {
                  "type": "text",
                  "text": "Canvas"
                }
              ]
            },
            {
              "type": "rich_text_section",
              "elements": [
                {
                  "type": "text",
                  "text": "Developing with Block Kit"
                }
              ]
            }
          ],
          "style": "bullet",
          "indent": 0,
          "border": 1
        }
      ]
    }
  ]
}
```

:%22%7D%5D%7D,%7B%22type%22:%22rich_text_list%22,%22elements%22:%5B%7B%22type%22:%22rich_text_section%22,%22elements%22:%5B%7B%22type%22:%22text%22,%22text%22:%22Huddles%22%7D%5D%7D,%7B%22type%22:%22rich_text_section%22,%22elements%22:%5B%7B%22type%22:%22text%22,%22text%22:%22Canvas%22%7D%5D%7D,%7B%22type%22:%22rich_text_section%22,%22elements%22:%5B%7B%22type%22:%22text%22,%22text%22:%22Developing%20with%20Block%20Kit%22%7D%5D%7D%5D,%22style%22:%22bullet%22,%22indent%22:0,%22border%22:1%7D%5D%7D%5D%7D)

Let's say we want to create a nested list, for example something that looks like this:

Breakfast foods I enjoy:

- Hashbrowns
- Eggs
    *   Scrambled
    *   Over easy
- Pancakes, extra syrup

To create that in rich text, create three instances of `rich_text_list`, the middle one using the `indent` property to indent the types of eggs into that sub-list.

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "block_id": "block1",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "text",
              "text": "Breakfast foods I enjoy:"
            }
          ]
        },
        {
          "type": "rich_text_list",
          "style": "bullet",
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [
                {
                  "type": "text",
                  "text": "Hashbrowns"
                }
              ]
            },
            {
              "type": "rich_text_section",
              "elements": [
                {
                  "type": "text",
                  "text": "Eggs"
                }
              ]
            }
          ]
        },
        {
          "type": "rich_text_list",
          "style": "bullet",
          "indent": 1,
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [
                {
                  "type": "text",
                  "text": "Scrambled"
                }
              ]
            },
            {
              "type": "rich_text_section",
              "elements": [
                {
                  "type": "text",
                  "text": "Over easy"
                }
              ]
            }
          ]
        },
        {
          "type": "rich_text_list",
          "style": "bullet",
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [
                {
                  "type": "text",
                  "text": "Pancakes, extra syrup"
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```


## Rich text preformatted element — `rich_text_preformatted`

Displays a preformatted rich text element.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of the sub-element; in this case, `rich_text_preformatted`. |
| `elements` | Object [] | Required | An array of [text](https://docs.slack.dev/reference/block-kit/block-elements/text-element) or [link](https://docs.slack.dev/reference/block-kit/block-elements/link-element) elements. |
| `border` | Number | Optional | Turn the border on or off. |
| `language` | String | Optional | The language of the code block, used for syntax highlighting (e.g., `"python"`, `"javascript"`, `"json"`). |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_preformatted",
          "elements": [
            {
              "type": "text",
              "text": "{\n  \"object\": {\n    \"description\": \"this is an example of a json object\"\n  }\n}"
            }
          ],
          "border": 0
        }
      ]
    }
  ]
}
```


## Rich text quote element — `rich_text_quote`

Displays a rich text quote block.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of the sub-element; in this case, `rich_text_quote`. |
| `elements` | Object [] | Required | An array of rich text elements. Rich text elements include [`attachment_mention`](https://docs.slack.dev/reference/block-kit/block-elements/attachment-mention-element), [`broadcast`](https://docs.slack.dev/reference/block-kit/block-elements/broadcast-element), [`canvas`](https://docs.slack.dev/reference/block-kit/block-elements/canvas-element), [`canvas_user_mention`](https://docs.slack.dev/reference/block-kit/block-elements/canvas-user-mention-element), [`canvas_message_unfurl`](https://docs.slack.dev/reference/block-kit/block-elements/canvas-message-unfurl-element), [`channel`](https://docs.slack.dev/reference/block-kit/block-elements/channel-element), [`citation`](https://docs.slack.dev/reference/block-kit/block-elements/citation-element), [`color`](https://docs.slack.dev/reference/block-kit/block-elements/color-element), [`date`](https://docs.slack.dev/reference/block-kit/block-elements/date-element), [`emoji`](https://docs.slack.dev/reference/block-kit/block-elements/emoji-element), [`file`](https://docs.slack.dev/reference/block-kit/block-elements/file-element), [`link`](https://docs.slack.dev/reference/block-kit/block-elements/link-element), [`list_record`](https://docs.slack.dev/reference/block-kit/block-elements/list-record-element), [`message_mention`](https://docs.slack.dev/reference/block-kit/block-elements/message-mention-element), [`salesforce_data_field`](https://docs.slack.dev/reference/block-kit/block-elements/salesforce-data-field-element), [`tag`](https://docs.slack.dev/reference/block-kit/block-elements/tag-element), [`team`](https://docs.slack.dev/reference/block-kit/block-elements/team-element), [`text`](https://docs.slack.dev/reference/block-kit/block-elements/text-element), [`user`](https://docs.slack.dev/reference/block-kit/block-elements/user-element), [`usergroup`](https://docs.slack.dev/reference/block-kit/block-elements/usergroup-element), [`work_object_mention`](https://docs.slack.dev/reference/block-kit/block-elements/work-object-mention-element), [`workflow_mention`](https://docs.slack.dev/reference/block-kit/block-elements/workflow-mention-element). |
| `border` | Number | Optional | Turn the border on or off. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "block_id": "Vrzsu",
      "elements": [
        {
          "type": "rich_text_quote",
          "elements": [
            {
              "type": "text",
              "text": "What we need is good examples in our documentation."
            }
          ]
        },
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "text",
              "text": "Yes - I completely agree, Luke!"
            }
          ]
        }
      ]
    }
  ]
}
```


## Rich text section element — `rich_text_section`

A section element that holds rich text elements.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of sub-element; in this case, `rich_text_section`. |
| `elements` | Object [] | Required | An array of rich text elements. Rich text elements include [`attachment_mention`](https://docs.slack.dev/reference/block-kit/block-elements/attachment-mention-element), [`broadcast`](https://docs.slack.dev/reference/block-kit/block-elements/broadcast-element), [`canvas`](https://docs.slack.dev/reference/block-kit/block-elements/canvas-element), [`canvas_user_mention`](https://docs.slack.dev/reference/block-kit/block-elements/canvas-user-mention-element), [`canvas_message_unfurl`](https://docs.slack.dev/reference/block-kit/block-elements/canvas-message-unfurl-element), [`channel`](https://docs.slack.dev/reference/block-kit/block-elements/channel-element), [`citation`](https://docs.slack.dev/reference/block-kit/block-elements/citation-element), [`color`](https://docs.slack.dev/reference/block-kit/block-elements/color-element), [`date`](https://docs.slack.dev/reference/block-kit/block-elements/date-element), [`emoji`](https://docs.slack.dev/reference/block-kit/block-elements/emoji-element), [`file`](https://docs.slack.dev/reference/block-kit/block-elements/file-element), [`link`](https://docs.slack.dev/reference/block-kit/block-elements/link-element), [`list_record`](https://docs.slack.dev/reference/block-kit/block-elements/list-record-element), [`message_mention`](https://docs.slack.dev/reference/block-kit/block-elements/message-mention-element), [`salesforce_data_field`](https://docs.slack.dev/reference/block-kit/block-elements/salesforce-data-field-element), [`tag`](https://docs.slack.dev/reference/block-kit/block-elements/tag-element), [`team`](https://docs.slack.dev/reference/block-kit/block-elements/team-element), [`text`](https://docs.slack.dev/reference/block-kit/block-elements/text-element), [`user`](https://docs.slack.dev/reference/block-kit/block-elements/user-element), [`usergroup`](https://docs.slack.dev/reference/block-kit/block-elements/usergroup-element), [`work_object_mention`](https://docs.slack.dev/reference/block-kit/block-elements/work-object-mention-element), [`workflow_mention`](https://docs.slack.dev/reference/block-kit/block-elements/workflow-mention-element). |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "text",
              "text": "Hello there, I am a basic rich text block!"
            }
          ]
        }
      ]
    },
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "text",
              "text": "Hello there, "
            },
            {
              "type": "text",
              "text": "I am a bold rich text block!",
              "style": {
                "bold": true
              }
            }
          ]
        }
      ]
    },
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "text",
              "text": "Hello there, "
            },
            {
              "type": "text",
              "text": "I am an italic rich text block!",
              "style": {
                "italic": true
              }
            }
          ]
        }
      ]
    },
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "text",
              "text": "Hello there, "
            },
            {
              "type": "text",
              "text": "I am a strikethrough rich text block!",
              "style": {
                "strike": true
              }
            }
          ]
        }
      ]
    }
  ]
}
```


## Salesforce data field element — `salesforce_data_field`

Renders as a Salesforce data field reference.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "salesforce_data_field". |
| `salesforce_record_id` | String | Required | The ID of the Salesforce record to reference. |
| `salesforce_field_label` | String | Optional | The Salesforce field label. |
| `salesforce_field_api_name` | String | Optional | The Salesforce field API name. |
| `salesforce_include_field_label` | Boolean | Optional | When true, display the field label before the field value. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "salesforce_data_field",
              "salesforce_record_id": "001ABC456DEF789"
            }
          ]
        }
      ]
    }
  ]
}
```


## Select menu element — `static_select` / `external_select` / `users_select` / `conversations_select` / `channels_select`

Allows users to choose an option from a drop down menu.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Section, Actions, Input

### Usage info

_Interactive component_ - see our [guide to enabling interactivity](https://docs.slack.dev/interactivity/handling-user-interaction).

The select menu also includes type-ahead functionality, where a user can type a part or all of an option string to filter the list.

There are different types of select menu elements that depend on different data sources for their lists of options:

- Select menu of static options
- Select menu of external data source
- Select menu of users
- Select menu of conversations
- Select menu of public channels

### Select menu of static options

This is the most basic form of select menu, with a static list of options passed in when defining the element.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `static_select`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `options` | Object[] | Required | An array of [option objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-object). Maximum number of options is 100. If `option_groups` is specified, this field should not be. |
| `option_groups` | Object[] | Optional | An array of [option group objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-group-object). Maximum number of option groups is 100. If `options` is specified, this field should not be. |
| `initial_option` | Object | Optional | A single option that exactly matches one of the options within `options` or `option_groups`. This option will be selected when the menu initially loads. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after a menu item is selected. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the menu. Maximum length for the `text` in this field is 150 characters. |

### Example

The select menu element must be used inside of the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block, [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block, or [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows a section block containing a static select menu.

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section678",
      "text": {
        "type": "mrkdwn",
        "text": "Pick an item from the dropdown list"
      },
      "accessory": {
        "action_id": "text1234",
        "type": "static_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select an item"
        },
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
          }
        ]
      }
    }
  ]
}
```

### Select menu of external data source

This select menu will load its options from an external data source, allowing for a dynamic list of options.

### Setup

If you don't have [Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode) enabled, you'll need to configure your app to use this menu type:

1.  Go to your [app's settings page](https://api.slack.com/apps) and select **Interactivity & Shortcuts** from the sidebar.
2.  Add a URL to the **Options Load URL** under Select Menus.
3.  Save changes.

Each time a select menu of this type is opened or the user starts typing in the typeahead field, we'll send a request to your specified URL. Your app should return an HTTP 200 OK response, along with an `application/json` post body with an object containing either:

- an [`options`](https://docs.slack.dev/reference/block-kit/composition-objects/option-object) array
- an [`option_groups`](https://docs.slack.dev/reference/block-kit/composition-objects/option-group-object) array

The `options` array can have a maximum number of 100 options.

The `option_groups` array can have a maximum number of 100 option groups, with each option group allowing up to 100 options.

Here's an example response:

```blockkit
{
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
    }
  ]
}
```

Refer to [`options`](https://docs.slack.dev/reference/block-kit/composition-objects/option-object) and [`option_groups`](https://docs.slack.dev/reference/block-kit/composition-objects/option-group-object) for more information about their related fields.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `external_select`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_option` | Object | Optional | A single option that exactly matches one of the options within the `options` or `option_groups` loaded from the external data source. This option will be selected when the menu initially loads. |
| `min_query_length` | Integer | Optional | When the typeahead field is used, a request will be sent on every character change. If you prefer fewer requests or more fully ideated queries, use the `min_query_length` attribute to tell Slack the fewest number of typed characters required before dispatch. The default value is `3`. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after a menu item is selected. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the menu. Maximum length for the `text` in this field is 150 characters. |

### Example

A select menu in a section block with an external data source:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section678",
      "text": {
        "type": "mrkdwn",
        "text": "Pick an item from the dropdown list"
      },
      "accessory": {
        "action_id": "text1234",
        "type": "external_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select an item"
        },
        "min_query_length": 3
      }
    }
  ]
}
```

### Select menu of users

This select menu will populate its options with a list of Slack users visible to the current user in the active workspace.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `users_select`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_user` | String | Optional | The user ID of any valid user to be pre-selected when the menu loads. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after a menu item is selected. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the menu. Maximum length for the `text` in this field is 150 characters. |

### Example

A select menu in a section block showing a list of users:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section678",
      "text": {
        "type": "mrkdwn",
        "text": "Pick a user from the dropdown list"
      },
      "accessory": {
        "action_id": "text1234",
        "type": "users_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select an item"
        }
      }
    }
  ]
}
```

### Select menu of conversations

This select menu will populate its options with a list of public and private channels, DMs, and MPIMs visible to the current user in the active workspace.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `conversations_select`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_conversation` | String | Optional | The ID of any valid conversation to be pre-selected when the menu loads. If `default_to_current_conversation` is also supplied, `initial_conversation` will take precedence. |
| `default_to_current_conversation` | Boolean | Optional | Pre-populates the select menu with the conversation that the user was viewing when they opened the modal, if available. Default is `false`. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after a menu item is selected. |
| `response_url_enabled` | Boolean | Optional | **This field only works with menus in [input blocks](https://docs.slack.dev/reference/block-kit/blocks/input-block) in [modals](https://docs.slack.dev/surfaces/modals).** When set to `true`, the [`view_submission` payload](https://docs.slack.dev/reference/interaction-payloads/view-interactions-payload#view_submission) from the menu's parent view will contain a `response_url`. This `response_url` can be used for [message responses](https://docs.slack.dev/interactivity/handling-user-interaction#message_responses). The target conversation for the message will be determined by the value of this select menu. |
| `filter` | Object | Optional | A [filter object](https://docs.slack.dev/reference/block-kit/composition-objects/conversation-filter-object) that reduces the list of available conversations using the specified criteria. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the menu. Maximum length for the `text` in this field is 150 characters. |

### Example

A select menu in a section block showing a list of conversations:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section678",
      "text": {
        "type": "mrkdwn",
        "text": "Pick a conversation from the dropdown list"
      },
      "accessory": {
        "action_id": "text1234",
        "type": "conversations_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select an item"
        }
      }
    }
  ]
}
```

### Select menu of public channels

This select menu will populate its options with a list of public channels visible to the current user in the active workspace.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `channels_select`. |
| `action_id` | String | Optional | An identifier for the action triggered when a menu option is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_channel` | String | Optional | The ID of any valid public channel to be pre-selected when the menu loads. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after a menu item is selected. |
| `response_url_enabled` | Boolean | Optional | **This field only works with menus in [input blocks](https://docs.slack.dev/reference/block-kit/blocks/input-block) in [modals](https://docs.slack.dev/surfaces/modals).** When set to `true`, the [`view_submission` payload](https://docs.slack.dev/reference/interaction-payloads/view-interactions-payload#view_submission) from the menu's parent view will contain a `response_url`. This `response_url` can be used for [message responses](https://docs.slack.dev/interactivity/handling-user-interaction#message_responses). The target channel for the message will be determined by the value of this select menu. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the menu. Maximum length for the `text` in this field is 150 characters. |

### Example

A select menu in a section block showing a list of channels:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section678",
      "text": {
        "type": "mrkdwn",
        "text": "Pick a channel from the dropdown list"
      },
      "accessory": {
        "action_id": "text1234",
        "type": "channels_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select an item"
        }
      }
    }
  ]
}
```


## Tag element — `tag`

Renders as a colored tag or pill.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "tag". |
| `text` | String | Required | The text displayed in the tag. |
| `color` | String | Optional | The color of the tag. The options for this value are: "gray", "brown", "purple", "indigo", "blue", "green", "yellow", "orange", "red". |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "tag",
              "text": "In progress"
            }
          ]
        }
      ]
    }
  ]
}
```


## Team element — `team`

Renders as a mention of a workspace or team.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "team". |
| `team_id` | String | Required | The ID of the workspace or team to mention. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "team",
              "team_id": "T123ABC456"
            }
          ]
        }
      ]
    }
  ]
}
```


## Text element — `text`

Displays text, optionally with styling.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "text". |
| `text` | String | Required | The text shown to the user. Not parsed: emoji shortcodes stay literal here, unlike `mrkdwn` in a section. See "Emoji shortcodes are not parsed here" below. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |

### Emoji shortcodes are not parsed here

A `:shortcode:` in a `text` element's `text` renders as the literal characters `:white_check_mark:`. The rich-text elements are a structured tree, not a markup string, and nothing substitutes an emoji into one.

Use the [emoji element](https://docs.slack.dev/reference/block-kit/block-elements/emoji-element) as a sibling instead:

```blockkit
{
  "type": "rich_text_section",
  "elements": [
    { "type": "emoji", "name": "white_check_mark" },
    { "type": "text", "text": " Done" }
  ]
}
```

A literal unicode emoji pasted into `text` does render. The element form is still preferred: it names the emoji rather than carrying a code point, and it does not depend on the encoding of whatever produced the payload.

This is the trap: **the same string behaves differently in two blocks.** `":white_check_mark: Done"` in a `section` block's `mrkdwn` text object renders a green tick; in a `rich_text` `text` element it renders the colons. Text moved from one to the other silently changes meaning — nothing is rejected, so there is no error to notice.

Verified against a live workspace.

### An observed rejection of a non-ASCII character

A multiplication sign `×` (U+00D7) inside a `text` element's `text` was refused with `invalid_blocks`. The identical payload with a plain letter `x` in its place was accepted.

Only that character was tested. The general rule is untested: which characters outside ASCII are refused, whether the refusal depends on the surrounding block, and whether it is the character or the encoding of the request that is at fault, are all unknown. Do not read this as "non-ASCII is rejected" — accented letters and unicode emoji were not among the characters that failed, and emoji in particular are known to render.

What it is safe to conclude: if a `rich_text` payload is refused with `invalid_blocks` and every field looks well-formed, substitute the ASCII equivalent of any typographic character in it — `x` for `×`, `-` for `—` — and try again.

### Example

```blockkit
{
  "type": "rich_text",
  "elements": [
    {
      "type": "rich_text_section",
      "elements": [
        {
          "type": "text",
          "text": "Hello there, "
        },
        {
          "type": "text",
          "text": "I am a bold rich text block!",
          "style": {
            "bold": true
          }
        }
      ]
    }
  ]
}
```


## Time picker element — `timepicker`

Allows users to enter numerical data into a single-line field.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Section, Actions, Input

### Usage info

_Interactive component_ - see our [guide to enabling interactivity](https://docs.slack.dev/interactivity/handling-user-interaction).

On desktop clients, this time picker will take the form of a dropdown list with free-text entry for precise choices. On mobile clients, the time picker will use native time picker UIs.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `timepicker`. |
| `action_id` | String | Optional | An identifier for the action triggered when a time is selected. You can use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_time` | String | Optional | The initial time that is selected when the element is loaded. This should be in the format `HH:mm`, where `HH` is the 24-hour format of an hour (00 to 23) and `mm` is minutes with leading zeros (00 to 59), for example `22:25` for 10:25pm. |
| `confirm` | Object | Optional | A [confirm object](https://docs.slack.dev/reference/block-kit/composition-objects/confirmation-dialog-object) that defines an optional confirmation dialog that appears after a time is selected. |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown on the time picker. Maximum length for the `text` in this field is 150 characters. |
| `timezone` | String | Optional | A string in the IANA format, e.g. "America/Chicago". The timezone is displayed to end users as hint text underneath the time picker. It is also passed to the app upon certain interactions, such as `view_submission`. |

### Example

The time picker element must be used inside of the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block, [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block, or [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows a section block containing a time picker element, with the initial time set to 11:40am:

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "block_id": "section1234",
      "text": {
        "type": "mrkdwn",
        "text": "Pick a date for the deadline."
      },
      "accessory": {
        "type": "timepicker",
        "timezone": "America/Los_Angeles",
        "action_id": "timepicker123",
        "initial_time": "11:40",
        "placeholder": {
          "type": "plain_text",
          "text": "Select a time"
        }
      }
    }
  ]
}
```


## URL input element — `url_text_input`

Allows user to enter a URL into a single-line field.

- **Surfaces:** Modals
- **Works with blocks:** Input

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `url_text_input`. |
| `action_id` | String | Optional | An identifier for the input value when the parent modal is submitted. You can use this when you receive a `view_submission` payload [to identify the value of the input element](https://docs.slack.dev/surfaces/modals#interactions). Should be unique among all other `action_id`s in the containing block. Maximum length is 255 characters. |
| `initial_value` | String | Optional | The initial value in the URL input when it is loaded. |
| `dispatch_action_config` | Object | Optional | A [dispatch configuration object](https://docs.slack.dev/reference/block-kit/composition-objects/dispatch-action-configuration-object) that determines when during text input the element returns a [`block_actions` payload](https://docs.slack.dev/reference/interaction-payloads/block_actions-payload). |
| `focus_on_load` | Boolean | Optional | Indicates whether the element will be set to auto focus within the [`view object`](https://docs.slack.dev/reference/views). Only one element can be set to `true`. Defaults to `false`. |
| `placeholder` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) only text object that defines the placeholder text shown in the URL input. Maximum length for the `text` in this field is 150 characters. |

### Example

The URL input element must be used inside of the [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block, like this:

```blockkit
{
  "blocks": [
    {
      "type": "input",
      "element": {
        "type": "url_text_input",
        "action_id": "url_text_input-action"
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


## URL source element — `url`

Displays a URL source for referencing within a task card block.

- **Surfaces:** Messages
- **Works with blocks:** Task card

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `url`. |
| `url` | String | Required | The URL type source. |
| `text` | String | Required | Display text for the URL. |

### Usage info

The URL source element is used to display clickable URL references within a [task card block](https://docs.slack.dev/reference/block-kit/blocks/task-card-block). It cannot be used within other blocks. Note that whether the URL actually resolves via DNS is not validated.

### Examples

A URL source element:

```blockkit
{
  "type": "url",
  "url": "https://docs.slack.dev/",
  "text": "Slack API docs"
}
```

Example within a task card block:

```blockkit
{
  "type": "task_card",
  "task_id": "task_1",
  "title": "Scientific findings",
  "status": "complete",
  "sources": [
    {
      "type": "url",
      "url": "https://docs.example.com/",
      "text": "Tracy's delightful docs"
    },
    {
      "type": "url",
      "url": "https://research.example.com/",
      "text": "Haley's resourceful research"
    }
  ]
}
```


## User element — `user`

Renders as a mention of a user.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "user". |
| `user_id` | String | Required | The ID of the user to be mentioned. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `underline`, and `unlink`. |
| `from_llm` | Boolean | Optional | Indicates whether the user was generated by the LLM itself. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "user",
              "user_id": "U123ABC456"
            }
          ]
        }
      ]
    }
  ]
}
```


## Usergroup element — `usergroup`

Renders as a mention of a user group.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case "usergroup". |
| `usergroup_id` | String | Required | The ID of the user group to be mentioned. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `unlink`, and `underline`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "usergroup",
              "usergroup_id": "G123ABC456"
            }
          ]
        }
      ]
    }
  ]
}
```


## Work object mention element — `work_object_mention`

Renders as a Work Object reference.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "work_object_mention". |
| `entity_id` | String | Required | The ID of the Work Object entity. |
| `app_id` | String | Required | The ID of the app associated with the Work Object. |
| `text` | String | Required | The display text for the Work Object reference. |
| `url` | String | Required | The URL of the Work Object. |
| `icon_url` | String | Optional | Optional product icon URL for the Work Object. |
| `full_size_preview_enabled` | Boolean | Optional | Whether the Work Object supports full size preview. |
| `product_name` | String | Optional | The product name for the Work Object. Used to determine per-product click behavior preferences. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `unlink`, and `underline`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "work_object_mention",
              "entity_id": "E123ABC456",
              "app_id": "A123ABC456",
              "text": "Work object",
              "url": "https://example.com/work-object"
            }
          ]
        }
      ]
    }
  ]
}
```


## Workflow button element — `workflow_button`

Allows users to run a link trigger with customizable inputs.

- **Surfaces:** Messages
- **Works with blocks:** Section, Actions

Example:

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of element. In this case `type` is always `workflow_button`. |
| `text` | Object | Required | A [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) that defines the button's text. Can only be of `type: plain_text`. `text` may truncate with ~30 characters. Maximum length for the `text` in this field is 75 characters. |
| `workflow` | Object | Required | A [workflow object](https://docs.slack.dev/reference/block-kit/composition-objects/workflow-object) that contains details about the workflow that will run when the button is clicked. |
| `action_id` | String | Required | An identifier for the action. Use this when you receive an interaction payload to [identify the source of the action](https://docs.slack.dev/interactivity/handling-user-interaction#payloads). Every `action_id` in a block should be unique. Maximum length is 255 characters. |
| `style` | String | Optional | Decorates buttons with alternative visual color schemes. Use this option with restraint.`primary` gives buttons a green outline and text, ideal for affirmation or confirmation actions. `primary` should only be used for one button within a set.`danger` gives buttons a red outline and text, and should be used when the action is destructive. Use `danger` even more sparingly than `primary`.If you don't include this field, the default button style will be used. |
| `accessibility_label` | String | Optional | A label for longer descriptive text about a button element. This label will be read out by screen readers _instead of_ the button [`text` object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object). Maximum length is 75 characters. |

### Example

The workflow button element must be used inside of the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block or the [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block. This example shows a section block containing a workflow button element.

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "text": "A message *with some bold text* and _some italicized text_.",
        "type": "mrkdwn"
      },
      "accessory": {
        "type": "workflow_button",
        "text": {
          "type": "plain_text",
          "text": "Run Workflow"
        },
        "action_id": "workflowbutton123",
        "workflow": {
          "trigger": {
            "url": "https://slack.com/shortcuts/Ft0123ABC456/xyz...zyx",
            "customizable_input_parameters": [
              {
                "name": "input_parameter_a",
                "value": "Value for input param A"
              },
              {
                "name": "input_parameter_b",
                "value": "Value for input param B"
              }
            ]
          }
        }
      }
    }
  ]
}
```


## Workflow mention element — `workflow_mention`

Renders as a link to a workflow.

- **Surfaces:** Messages, Modals, Home tabs
- **Works with blocks:** Rich text

This is a rich text element, compatible only with the [`rich_text`](https://docs.slack.dev/reference/block-kit/blocks/rich-text-block) block. It must be used within the [`rich_text_list`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-list-element), [`rich_text_quote`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-quote-element), or [`rich_text_section`](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-section-element) block element within the `rich_text` block's `elements` array.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The type of object; in this case, "workflow_mention". |
| `workflow_id` | String | Required | The ID of the workflow to link to. |
| `function_trigger_id` | String | Required | The ID of the function trigger for the workflow. |
| `text` | String | Required | The display text for the workflow link. |
| `url` | String | Optional | URL of the workflow. |
| `channel_id` | String | Optional | The encoded channel ID where this workflow mention lives. |
| `ts` | String | Optional | The encoded message timestamp where this workflow mention lives. |
| `style` | Object | Optional | An object of optional boolean properties that dictate style: `bold`, `italic`, `strike`, `highlight`, `client_highlight`, `unlink`, and `underline`. |

### Example

```blockkit
{
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {
              "type": "workflow_mention",
              "workflow_id": "Wf123ABC456",
              "function_trigger_id": "Ft123ABC456",
              "text": "Run workflow"
            }
          ]
        }
      ]
    }
  ]
}
```
