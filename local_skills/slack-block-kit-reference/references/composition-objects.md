# Composition objects

Composition objects are the small reusable JSON shapes that blocks and elements embed: text, options, confirmation dialogs, filters and so on. They are not blocks and never appear at the top level of a `blocks` array.

## Contents

- Confirmation dialog object
- Conversation filter object
- Dispatch action configuration object
- Option group object
- Option object
- Slack file object
- Slack icon object
- Text object — `plain_text` / `mrkdwn`
- Trigger object
- Workflow object
- Input parameter object

---

## Confirmation dialog object

Provides a dialog that adds a confirmation step to interactive elements.

An object that defines a dialog that provides a confirmation step to any interactive element. This dialog will ask the user to confirm their action by offering a confirm and deny buttons.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | Object | Required | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) text object that defines the dialog's title. Maximum length for this field is 100 characters. |
| `text` | Object | Required | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) text object that defines the explanatory text that appears in the confirm dialog. Maximum length for the `text` in this field is 300 characters. |
| `confirm` | Object | Required | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) text object to define the text of the button that confirms the action. Maximum length for the `text` in this field is 30 characters. |
| `deny` | Object | Required | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) text object to define the text of the button that cancels the action. Maximum length for the `text` in this field is 30 characters. |
| `style` | String | Optional | Defines the color scheme applied to the `confirm` button. A value of `danger` will display the button with a red background on desktop, or red text on mobile. A value of `primary` will display the button with a green background on desktop, or blue text on mobile. If this field is not provided, the default value will be `primary`. |

### Example

The confirmation dialog object must be used within an interactive element. It is shown here within the [button](https://docs.slack.dev/reference/block-kit/block-elements/button-element) element.

```blockkit
{
  "blocks": [
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "emoji": true,
            "text": "Approve"
          },
          "confirm": {
            "title": {
              "type": "plain_text",
              "text": "Are you sure?"
            },
            "text": {
              "type": "mrkdwn",
              "text": "Would you not prefer a good game of _chess_?"
            },
            "confirm": {
              "type": "plain_text",
              "text": "Do it"
            },
            "deny": {
              "type": "plain_text",
              "text": "Stop, I changed my mind!"
            }
          },
          "style": "primary",
          "value": "click_me_123"
        },
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "emoji": true,
            "text": "Deny"
          },
          "style": "danger",
          "value": "click_me_123"
        }
      ]
    }
  ]
}
```


## Conversation filter object

Provides a way to filter the list of options in conversation selector menus.

The menu can be either a [conversations select menu](https://docs.slack.dev/reference/block-kit/block-elements/select-menu-element#conversations_select) or a [conversations multi-select menu](https://docs.slack.dev/reference/block-kit/block-elements/multi-select-menu-element).

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `include` | String[] | Optional | Indicates which type of conversations should be _included_ in the list. When this field is provided, any conversations that do not match will be excludedYou should provide an array of strings from the following options: `im`, `mpim`, `private`, and `public`. The array cannot be empty. |
| `exclude_external_shared_channels` | Boolean | Optional | Indicates whether to exclude external [shared channels](https://docs.slack.dev/apis/slack-connect/) from conversation lists. This field will not exclude users from shared channels. Defaults to `false`. |
| `exclude_bot_users` | Boolean | Optional | Indicates whether to exclude bot users from conversation lists. Defaults to `false`. |

Please note that while none of the fields above are individually required, **you must supply at least one of these fields**.

### Example

The conversations select composition object must be used within the [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block, [actions](https://docs.slack.dev/reference/block-kit/blocks/actions-block) block, or [input](https://docs.slack.dev/reference/block-kit/blocks/input-block) block. This example shows an input block containing the conversations select object.

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
      "element": {
        "type": "conversations_select",
        "placeholder": {
          "type": "plain_text",
          "text": "Select a conversation",
          "emoji": true
        },
        "filter": {
          "include": [
            "public",
            "mpim"
          ],
          "exclude_bot_users": true
        }
      },
      "label": {
        "type": "plain_text",
        "text": "Choose the conversation to publish your result to:",
        "emoji": true
      }
    }
  ]
}
```

### Known issues

- In iOS, the placeholder text is replaced with "0 selected" when there are no selected conversations.

- In iOS, there are UI inconsistencies when users select items in multi-select menus.


## Dispatch action configuration object

Defines when a plain-text input element will return a `block_actions` interaction payload.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `trigger_actions_on` | String[] | Optional | An array of interaction types that you would like to receive a [`block_actions` payload](https://docs.slack.dev/reference/interaction-payloads/block_actions-payload) for. Should be one or both of:`on_enter_pressed` — payload is dispatched when user presses the enter key while the input is in focus. Hint text will appear underneath the input explaining to the user to press enter to submit.`on_character_entered` — payload is dispatched when a character is entered (or removed) in the input. |

### Example

The dispatch action configuration object must be used with a [plain-text input](https://docs.slack.dev/reference/block-kit/block-elements/plain-text-input-element) element or [rich text input](https://docs.slack.dev/reference/block-kit/block-elements/rich-text-input-element/) element.

```blockkit
{
  "blocks": [
    {
      "type": "input",
      "dispatch_action": true,
      "element": {
        "type": "plain_text_input",
        "multiline": true,
        "dispatch_action_config": {
          "trigger_actions_on": [
            "on_character_entered"
          ]
        }
      },
      "label": {
        "type": "plain_text",
        "text": "This is a multiline plain-text input",
        "emoji": true
      }
    }
  ]
}
```


## Option group object

Used to group option objects in select menus.

The menu can be a [select menu](https://docs.slack.dev/reference/block-kit/block-elements/select-menu-element) or a [multi-select menu](https://docs.slack.dev/reference/block-kit/block-elements/multi-select-menu-element). An `option_groups` array can have a maximum number of 100 option groups with a maximum of 100 options.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `label` | Object | Required | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) text object that defines the label shown above this group of options. Maximum length for the `text` in this field is 75 characters. |
| `options` | Object[] | Required | An array of [option objects](https://docs.slack.dev/reference/block-kit/composition-objects/option-object) that belong to this specific group. Maximum of 100 items. |

### Example

The option group object must be used with the [select](https://docs.slack.dev/reference/block-kit/block-elements/select-menu-element) menu element or the [multi-select](https://docs.slack.dev/reference/block-kit/block-elements/multi-select-menu-element) menu element. This example shows a static select menu containing the option group object.

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": ":mag: Search results for *Cata*"
      }
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*<fakeLink.toYourApp.com|Use Case Catalogue>*\nUse Case Catalogue for the following departments/roles..."
      },
      "accessory": {
        "type": "static_select",
        "placeholder": {
          "type": "plain_text",
          "emoji": true,
          "text": "Manage"
        },
        "option_groups": [
          {
            "label": {
              "type": "plain_text",
              "text": "Group 1"
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
          },
          {
            "label": {
              "type": "plain_text",
              "text": "Group 2"
            },
            "options": [
              {
                "text": {
                  "type": "plain_text",
                  "text": "*this is plain_text text*"
                },
                "value": "value-3"
              }
            ]
          }
        ]
      }
    }
  ]
}
```


## Option object

Represents a single item in a number of item selection elements.

An object that represents a single selectable item in a [select menu](https://docs.slack.dev/reference/block-kit/block-elements/select-menu-element), [multi-select menu](https://docs.slack.dev/reference/block-kit/block-elements/multi-select-menu-element), [checkbox group](https://docs.slack.dev/reference/block-kit/block-elements/checkboxes-element), [radio button group](https://docs.slack.dev/reference/block-kit/block-elements/radio-button-group-element), or [overflow menu](https://docs.slack.dev/reference/block-kit/block-elements/overflow-menu-element).

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | Object | Required | A [text object](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) that defines the text shown in the option on the menu. Overflow, select, and multi-select menus can only use `plain_text` objects, while radio buttons and checkboxes can use `mrkdwn` text objects. Maximum length for the `text` in this field is 75 characters. |
| `value` | String | Required | A unique string value that will be passed to your app when this option is chosen. Maximum length for this field is 150 characters. |
| `description` | Object | Optional | A [`plain_text`](https://docs.slack.dev/reference/block-kit/composition-objects/text-object) text object that defines a line of descriptive text shown below the `text` field beside a single selectable item in a [select menu](https://docs.slack.dev/reference/block-kit/block-elements/select-menu-element), [multi-select menu](https://docs.slack.dev/reference/block-kit/block-elements/multi-select-menu-element), [checkbox group](https://docs.slack.dev/reference/block-kit/block-elements/checkboxes-element), [radio button group](https://docs.slack.dev/reference/block-kit/block-elements/radio-button-group-element), or [overflow menu](https://docs.slack.dev/reference/block-kit/block-elements/overflow-menu-element). [Checkbox group](https://docs.slack.dev/reference/block-kit/block-elements/checkboxes-element) and [radio button group](https://docs.slack.dev/reference/block-kit/block-elements/radio-button-group-element) items can also use [`mrkdwn`](https://docs.slack.dev/messaging/formatting-message-text#basic-formatting) formatting. Maximum length for the `text` within this field is 75 characters. |
| `url` | String | Optional | A URL to load in the user's browser when the option is clicked. **The `url` attribute is only available in [overflow menus](https://docs.slack.dev/reference/block-kit/block-elements/overflow-menu-element)**. Maximum length for this field is 3000 characters. If you're using `url`, you'll still receive an [interaction payload](https://docs.slack.dev/interactivity/handling-user-interaction#payloads) and will need to [send an acknowledgement response](https://docs.slack.dev/interactivity/handling-user-interaction#acknowledgment_response). |

### Example

```blockkit
{
  "text": {
    "type": "plain_text",
    "emoji": true,
    "text": "Save it"
  },
  "value": "value-2"
}
```

The option object must be used with the [select menu](https://docs.slack.dev/reference/block-kit/block-elements/select-menu-element), [multi-select menu](https://docs.slack.dev/reference/block-kit/block-elements/multi-select-menu-element), [checkbox group](https://docs.slack.dev/reference/block-kit/block-elements/checkboxes-element), [radio button group](https://docs.slack.dev/reference/block-kit/block-elements/radio-button-group-element), or [overflow menu](https://docs.slack.dev/reference/block-kit/block-elements/overflow-menu-element).

This example shows a section block containing a static select menu element with several option objects.

```blockkit
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": ":mag: Search results for *Cata*"
      }
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*<fakeLink.toYourApp.com|Use Case Catalogue>*\nUse Case Catalogue for the following departments/roles..."
      },
      "accessory": {
        "type": "static_select",
        "placeholder": {
          "type": "plain_text",
          "emoji": true,
          "text": "Manage"
        },
        "options": [
          {
            "text": {
              "type": "plain_text",
              "emoji": true,
              "text": "Edit it"
            },
            "value": "value-0"
          },
          {
            "text": {
              "type": "plain_text",
              "emoji": true,
              "text": "Read it"
            },
            "value": "value-1"
          },
          {
            "text": {
              "type": "plain_text",
              "emoji": true,
              "text": "Save it"
            },
            "value": "value-2"
          }
        ]
      }
    }
  ]
}
```


## Slack file object

Defines an object containing Slack file information to be used in an image block or image element.

This [file](https://docs.slack.dev/reference/objects/file-object) must be an image and you must provide either the URL or ID. In addition, the user posting these blocks must have access to this file. If both are provided then the payload will be rejected. Currently only `png`, `jpg`, `jpeg`, and `gif` Slack image files are supported.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | Optional | This URL can be the `url_private` or the `permalink` of the Slack file. |
| `id` | string | Optional | Slack ID of the file. |

### Example

The Slack file object must be used within the [image](https://docs.slack.dev/reference/block-kit/blocks/image-block) block.

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


## Slack icon object

Defines an object containing Slack icon information to be used in a card block.

The Slack icon object must be used within the [card](https://docs.slack.dev/reference/block-kit/blocks/card-block) block, as the value of its `slack_icon` field. It is not valid anywhere else. It is also mutually exclusive with the card's `icon` field: the two render in the same position, so at most one of them may be present.

This object is absent from Slack's composition-objects index. The only link to its reference page is from the `slack_icon` row of the card block's field table.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Required | Always the literal string `icon`. It is never `slack_icon`; `slack_icon` is the name of the card field that holds this object, not the object's own type. |
| `name` | string | Required | Which icon to render. One of the 54 values listed below. The field is called `name` — there is no `icon` field inside this object. |

### Icon names

`name` takes one of exactly 54 documented values. This is a closed set with no derivable pattern, so a name has to be read off this list rather than guessed; an undocumented name is rejected along with the rest of the payload.

`archive`, `book`, `bookmark`, `bot`, `bug`, `calendar`, `call`, `caret-left`, `caret-right`, `check`, `clipboard`, `code`, `comment`, `compass`, `copy`, `cube`, `download`, `edit`, `email`, `eye-closed`, `eye-open`, `file`, `flag`, `folder`, `gear`, `globe`, `heart`, `help`, `image`, `info`, `key`, `lightbulb`, `link`, `map`, `mobile`, `new-window`, `pin`, `plus`, `refine`, `refresh`, `rocket`, `save`, `screen`, `share`, `sparkle`, `star`, `star-filled`, `tag`, `thumbs-down`, `thumbs-up`, `trash`, `upload`, `user`, `warning`

Names that look plausible but are not in the set include `sparkles` (the documented value is singular, `sparkle`), `alert`, `clock`, `document`, `search`, `settings` and `x`. There are no emoji names here: this list has nothing to do with the `:emoji:` shortcodes used in message text.

This list belongs to the card block alone. The [icon button element](https://docs.slack.dev/reference/block-kit/block-elements/icon-button-element) also has an `icon` field, but that one is a bare string, not an object, and `trash` is the only value it accepts.

### Example

The Slack icon object must be used within the [card](https://docs.slack.dev/reference/block-kit/blocks/card-block) block.

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
      "body": {
        "type": "mrkdwn",
        "text": "Please enjoy each card equally."
      }
    }
  ]
}
```


## Text object — `plain_text` / `mrkdwn`

Defines text for many different blocks and elements.

Formatted either as `plain_text` or using [`mrkdwn`](https://docs.slack.dev/messaging/formatting-message-text), our proprietary contribution to the much beloved [Markdown standard](https://xkcd.com/927/).

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | String | Required | The formatting to use for this text object. Can be one of `plain_text`or `mrkdwn`. |
| `text` | String | Required | The text for the block. This field accepts any of the standard [text formatting markup](https://docs.slack.dev/messaging/formatting-message-text) when `type` is `mrkdwn`. The minimum length is 1 and maximum length is 3000 characters. |
| `emoji` | Boolean | Optional | Indicates whether emojis in a text field should be escaped into the colon emoji format. This field is only usable when `type` is `plain_text`. |
| `verbatim` | Boolean | Optional | When set to `false` (as is default) URLs will be auto-converted into links, conversation names will be link-ified, and certain mentions will be [automatically parsed](https://docs.slack.dev/messaging/formatting-message-text#automatic-parsing). When set to `true`, Slack will continue to process all markdown formatting and [manual parsing strings](https://docs.slack.dev/messaging/formatting-message-text#advanced), but it won’t modify any plain-text content. For example, channel names will not be hyperlinked. This field is only usable when `type` is `mrkdwn`. |

### Example

The text object must be used within another block or element, such as the [header](https://docs.slack.dev/reference/block-kit/blocks/header-block) block, [section](https://docs.slack.dev/reference/block-kit/blocks/section-block) block, [button](https://docs.slack.dev/reference/block-kit/block-elements/button-element) element, [icon](https://docs.slack.dev/reference/block-kit/block-elements/icon-button-element) button element, or [workflow button](https://docs.slack.dev/reference/block-kit/block-elements/workflow-button-element) element. This example shows a section block containing a text object.

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


## Trigger object

Defines an object containing trigger information.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | String | Required | A [link trigger URL](https://docs.slack.dev/tools/deno-slack-sdk/guides/creating-link-triggers). Must be associated with a valid trigger. |
| `customizable_input_parameters` | Object[] | Optional | An array of input parameter objects. Each specified name must match an input parameter defined on the workflow of the provided trigger (url), and the input parameter mapping on the trigger must be set as `customizable: true`. Each specified value must match the type defined by the workflow input parameter of the matching name. |

The values used for these `customizable_input_parameters` may be visible client-side to end users. You should not share sensitive information or secrets via these input parameters.

### Example

A trigger object must be used inside of a [workflow](https://docs.slack.dev/reference/block-kit/composition-objects/workflow-object) object.

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


## Workflow object

Defines an object containing workflow information.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `trigger` | Object | Required | A [`trigger`](https://docs.slack.dev/reference/block-kit/composition-objects/trigger-object) object that contains information about a workflow's trigger. |

### Example

A workflow object must be used inside of a [workflow button](https://docs.slack.dev/reference/block-kit/block-elements/workflow-button-element) element.

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



## Input parameter object

Defines an object containing information about an input parameter.

Slack's composition-object index lists an "Input parameter object" page, but that page is not
published: the reference index links to it and the link 404s. The shape below is therefore taken
from the worked example on the trigger object page, which is where input parameter objects are
actually used, rather than from a fields table.

An input parameter object appears only inside a trigger object's `customizable_input_parameters`
array, which in turn appears inside a workflow object on a `workflow_button` element.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | String | Required | The name of an input parameter defined on the workflow behind the trigger. The trigger's input parameter mapping for that name must be set as `customizable: true`. |
| `value` | String | Required | The value to pass for that input parameter. Must match the type declared by the workflow input parameter of the same name. |

Values passed here may be visible client-side to end users, so they must not carry secrets.

```blockkit
{
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
```
