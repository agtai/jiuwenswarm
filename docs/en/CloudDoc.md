# Cloud-document co-editing (Co-scribe)

## 1. Overview

Co-scribe makes an agent a collaborator inside a shared cloud document. You share the document with the agent's service-account address, mention it in a comment, and it proposes an edit in that comment thread. Nothing is written to the body until a human replies with the approval word.

The loop stays in the document — there is no copying text into chat and pasting a revision back.

```
You            @co-scribe  please tighten this sentence
Agent          ⏳ Working on it…
Agent          [Proposed edit 1/1]  Original: … / Proposed: … / Note: why
You            approve
Agent          Applied the proposed edit.        ← the body changes here, not earlier
```

Google Docs is the only supported platform in this release. Everything provider-specific sits behind one interface, so a second platform is a matter of implementing it rather than reworking the loop.

**Disabled by default.** When `clouddoc.enabled` is `false`, the background service is never constructed and the Google libraries are never imported.

## 2. Quick start

### 2.1 Create a service account

The agent needs an identity of its own — not yours. A Google Cloud service account gives it one, keeps its credentials with you, and makes its edits distinguishable from yours in the document's revision history.

1. In the [Google Cloud console](https://console.cloud.google.com/), create a project (or pick one).
2. Enable both the **Google Docs API** and the **Google Drive API** for it.
3. Create a service account, then create a **JSON key** for it and download the file.
4. Note the service account's email address — it looks like `name@project-id.iam.gserviceaccount.com`. That address is the agent's identity in every document.

Keep the JSON key file outside the repository. Anyone holding it can act as the agent.

### 2.2 Share the document

Share your document with the service-account address exactly as you would with a colleague, and give it **Editor** access.

**Sharing is what puts a document under management.** Opening the Docs panel -- or pressing Refresh -- adopts every document shared with that account which it can actually edit, so there is no coming back to paste a link. Sharing is already a deliberate grant; a second confirmation would be ceremony. What makes it safe is that **watching costs only polling**: an adopted document spends no turn until somebody assigns a comment to the agent.

**Commenter access is not enough**, and the failure is quiet rather than loud. Without edit rights Google stops returning a revision id, which is what the concurrency protection depends on, and the permission listing starts returning 403, which is what the link-sharing warning depends on. Comment reading still works — so the agent would appear to function, propose edits normally, and never be able to apply one. Co-scribe refuses to watch such a document and says so at startup.

### 2.3 Configure

```yaml
clouddoc:
  enabled: true
  connections:
    - credentials_file: /secure/path/to/service-account.json
      documents:
        - https://docs.google.com/document/d/<doc-id>/edit    # link or bare id
```

One connection is one service account. Add more connections to have separate identities watch separate documents -- **a document belongs to exactly one connection**; duplicates are skipped at startup with a warning, since two identities watching one document answer every mention twice.

> The earlier shape (top-level `credentials_file` and `documents`) still works and means a single connection; adding or removing anything from the UI upgrades it to the shape above.

Restart the gateway. The startup log confirms the watcher is running:

```
[App] clouddoc watcher started for 1 document(s)
```

Only `credentials_file` has to be set here: **documents can be added from the UI**, below.

### 2.4 Managing documents in the UI

The **Docs** panel in the sidebar is the day-to-day entry point. Connections (provider x service account) on the left, the documents watched under the selected one on the right.

- **The address to share** sits in the right-hand header; hover it for Copy, then paste it into the document's Share dialog -- no digging through the JSON key.
- **Adopted automatically**: opening the panel or pressing Refresh brings in every shared document the account can edit. Ones shared comment-only are listed separately with the fix -- that is the single most common slip, and hiding it just reads as "sharing didn't work".
- **Adding by hand**: for a document the listing does not cover (the Drive API not enabled, say), paste its link into the box at the bottom. **Pasting verifies immediately** -- a document you can edit is watched right away; comment-only access says so and names the fix; a document not yet shared with the address tells you to share it first.
- **Per-document status**: OK / comment-only / frozen, each explained on hover. The three small dots in the header are the counts by status.
- **Refresh** re-checks every document's permission. **Fixing a permission and pressing it is how a document recovers**, including one that was paused after repeated failures.
- **Clicking a document card** opens it in Google Docs under your own account, not the agent's.

Adds and removals from the UI are written back to `config.yaml` and take effect immediately -- no restart.

### 2.5 Use it

Select a passage, add a comment, and type `@` followed by the service-account address — Google's autocomplete will offer it once the document is shared with it. **Then tick "Assign to".**

**Only an assignment triggers.** A mention on its own is a **marker**, not a handover:

| What you do | Meaning | Result |
|---|---|---|
| `@` it | A marker: this concerns the agent | No trigger. It answers once, pointing you at assignment or at the chat |
| `@` it **and assign it to it** | A handover: this is its task | Triggers. Placeholder, proposal, your approval, applied |
| "Mark as done" | Finished | Leaves the queue; no further triggers |

Two concrete reasons for the split. First, **an assignment names one account**, so a document can hold several agents that each see only their own work — while anyone may mention anyone, and a mention should not amount to handing work over. Second, whether a comment is a task is now **visible in the document**: an assigned comment shows as a to-do, with its owner on it.

Then reply in the thread:

| Reply | Effect |
|---|---|
| `同意` / `approve` | The proposal is applied to the body |
| `原文` / `keep` | The proposal is dropped, the text stays as it is |
| anything else | Treated as new feedback; the agent revises and proposes again |

**Language.** Comment in English or Chinese; the agent answers in the language you used. The two words it asks you to type back — `approve` and `keep` — stay English whatever the conversation is in, because they are commands rather than prose: one spelling to remember, and nothing to guess at in a Chinese thread. The Chinese words still work (matching accepts both lists); the prompt just shows one spelling.

Matching is **exact** after normalization. `approve the first one` and `approve, but reword the second sentence` are both new feedback, not approval — this is deliberate, and it fails toward asking one more round rather than applying something you did not mean.

## 3. Usage guidance

**Start a thread with a top-level comment that mentions the agent and is assigned to it.**

**Continuing in the same thread needs no second assignment.** While a thread is assigned and not marked done, every new reply in it reaches the agent. Withdraw the assignment or mark it done and the thread goes quiet.

**Another agent's post never wakes it.** Nothing written by a service account is a trigger -- neither its own posts nor another agent's. Otherwise two agents in one thread would answer each other without end, each turn producing the reply that triggers the next.

**Edit the text and the comments on it fall away.** Once you, someone else, or the agent working from chat changes a passage, comments anchored to it can no longer be located and any open proposal no longer applies. The agent says so and asks you to comment on the current text. This is deliberate: the words are gone, so edits aimed at them should not survive.

**Select the passage you want changed.** The selection is not just context, it is the boundary: an approved proposal can only change text inside the quoted range plus a small adjacent margin. This is what keeps "someone commented on one sentence" from becoming "the agent rewrote the section".

**Whole-document work happens in chat, within limits.** A comment's scope is its selection; to rewrite broadly, say so in the Jiuwen chat (section 8). **Generating content into an empty document** also happens in chat, and produces plain text only -- heading styles and bold are yours to apply.

**Formatting is not available.** The text the agent works with is plain text, so bold, italics, headings and colours cannot be changed from a comment. Ask for wording changes and set the formatting yourself.

**Everyone you share with can drive it.** Google's comment permissions carry no reliable author identity, so Co-scribe cannot restrict who may trigger the agent or who may approve its proposals — anyone with comment access can do both. Treat the sharing list as the authorization list. If the document is shared as "anyone with the link", that extends to anyone holding the link, and Co-scribe warns about that posture at startup.

## 4. Configuration

### 4.1 `config.yaml`

```yaml
clouddoc:
  enabled: false
  connections:
    - credentials_file: ""        # service-account JSON key path
      documents: []               # links or bare document ids

  # everything below is shared by all connections
  poll_interval_seconds: 30       # Drive has no push channel for comments
  turn_timeout_seconds: 540       # clamped below the transport ceiling at startup
  session_max_turns: 50           # rotate the document's session after this many turns

  conventions_marker: "co-scribe 约定"

  approve_word: ["同意", "approve"]   # word lists: a reply must equal one entry exactly
  keep_word: ["原文", "keep"]

  rail:
    adjacent_budget: 200          # how far outside the quoted range an edit may reach
    max_quote_chars: 400
    max_insert_chars: 2000
    max_edits: 10
```

Every configurable string — the conventions marker and **each entry** of the two word lists — must not equal or prefix any other, including two entries of the same list. This is checked at startup and the feature refuses to run if it fails: a collision across the two lists would make one reply mean both apply and don't.

> Earlier versions had a `trigger_word` (default `co-scribe:`) that fired on any comment starting with it. It is gone: that word **carries no identity**, so one comment beginning with it triggered **every** deployment watching the document — the ordinary situation in a shared document where several people bring their own agent.

### 4.2 Permissions

If your deployment sets `permissions.enabled: true`, the four tools the unattended path uses must be `allow`:

```yaml
permissions:
  tools:
    clouddoc_read: allow
    clouddoc_list_comments: allow
    clouddoc_propose_edit: allow
    clouddoc_reply_comment: allow
```

An unattended turn has nobody to answer a confirmation, so `ask` resolves to a refusal rather than a prompt. Setting any of these to `ask` disables the feature silently.

Two more are registered on the chat path only and **never on the unattended path**, so
their settings affect chat alone:

* `clouddoc_batch_edit` (editing the body directly) defaults to `ask`.
* `clouddoc_list_documents` (the documents this connection watches) defaults to `allow`.
  The chat path gets no doc_id, so without it the agent can only ask the user to paste a
  link -- while the panel is listing that very document. It stays out of the unattended
  allowlist: a comment-triggered turn is scoped to the document that triggered it, and
  handing it the full list would widen what it can see.

**With several documents managed, choosing one is a rail, not a prompt.** When the
connection watches two or more and the target's title, link or id appears nowhere in text
the user typed, every document operation -- read, list comments, edit, propose, reply --
is refused and the model is told to ask. The evidence is only ever **text the user typed**:
the model chose the doc_id being checked, so treating that as proof would be circular. An
`ask_user` answer counts, which is what lets a refused turn recover. Unattended turns are
exempt, since the gateway binds their document.

`clouddoc_list_documents` marks the one the user has already named in this session with
`user_named=true`, so the model knows **before** it picks rather than being corrected
after.

> Earlier versions also had `clouddoc_edit` and `clouddoc_resolve_comment`. The first was replaced by `clouddoc_batch_edit`, which submits several changes atomically and asks once. The second was removed: **closing a comment is the commenter's acceptance**, and having the agent do it means declaring acceptance on someone else's behalf -- which a shared service-account identity cannot establish the standing for.

## 5. Document conventions

A collaborator can set per-document writing conventions by leaving a top-level comment that starts with the conventions marker:

```
co-scribe 约定
Keep sentences short.
Use the full product name on first mention.
```

These bind **style only**. Anything in them that tries to change how the agent works — what it may edit, which tools it may use, whose approval counts — is ignored. Replies never count as conventions, so comment-only access cannot inject policy. When several such comments exist, the earliest wins.

The agent's own response policy is fixed in this release and not configurable; document conventions affect writing style only.

## 6. Limits

- **Anchoring**: Google's comment API returns the quoted text but no index. When that text appears more than once in the document, the agent cannot resolve which occurrence you meant and will ask you to re-comment.
- **Latency**: polling every 30 seconds means roughly 15 seconds of average trigger delay.
- **Quota**: all watched documents share the service account's quota. Watched documents are polled concurrently, so a slow turn on one does not delay the others.
- **One gateway**: the watcher assumes a single gateway instance. Two instances sharing a state file would each dispatch the same trigger.
- **Cost**: every trigger is one agent turn. A deployment watching many active documents should size that against its model budget.
- **Workspace policy**: some Google Workspace tenants forbid adding out-of-domain service accounts as collaborators. The workaround is an in-domain service account created by your own administrator.

## 7. Troubleshooting

| Symptom | Cause |
|---|---|
| Nothing happens after mentioning the agent | **A mention alone does not trigger — assign it.** The agent posts a one-line reply under the comment saying so; if even that is missing, the document is not watched (check the Docs panel, or `connections[].documents`), or the config was hand-edited without restarting the gateway (panel edits need no restart) |
| Assigned, and still nothing | Has the comment been marked done? Done means out of the queue. It may also be assigned to **another** agent's address |
| Startup log says the feature did not start | Credentials unreadable, document id unparseable, or two configurable strings collide — the log names which |
| Proposals appear but approval does nothing | Check that the reply is exactly one of the approval words. `同意实施` is new feedback, not approval |
| Tempted to add `ok`/`yes` as approval words | Don't: they are conversational acknowledgements. Someone meaning "I've seen it" would apply the edit. Approval words should only be words that commit |
| "the quoted range can no longer be located uniquely…" | The quoted text changed or appears more than once since the comment was written. Re-comment on the current text |
| The document stays silent after you fixed its permission (or restored sharing) | A document that failed repeatedly stops being polled. Press **Refresh** in the Docs panel — it re-checks each document and un-freezes the ones that now pass. Without the UI, restarting the gateway does the same thing once per start |
| "Could not apply: …" | The proposal reached outside the quoted range, or tried to introduce formatting markers into a plain-text body |

## 8. Working on a document from chat

Assignment inside the document is one path; operating on it from the Jiuwen chat is the other. Both write to the same document, and the split is simple: **assigned work belongs to the document side, everything else to chat**.

From chat the agent can:

- **read the document and list comments** — including those that merely mention it
- **reply to comments** (except resolved ones)
- **edit the body directly**: several changes, one atomic submission
- **write the first draft into an empty document**

From chat it cannot:

- **close a comment.** That is the commenter's acceptance to give
- **touch assigned work.** That belongs to the document side, and it skips those
- **write markdown.** The body is plain text, so `##`, `- ` and `**bold**` land as those characters. Write section titles as ordinary lines and apply styles yourself

### Two boundaries against the document side

**No body edits from chat while assigned work is outstanding.** Not because anchors would break -- that is defined behaviour -- but because two writers on one document produce work that is thrown away. Finish or close the assigned items first.

**A broad rewrite invalidates existing comments.** Their quoted text can no longer be found, so those threads stop being actionable; they remain readable, but reaching the agent needs a fresh comment on the current text.

### The two paths do not have the same safety model, on purpose

| | Document side (assignment) | Chat |
|---|---|---|
| Tools | closed set of four | five |
| Scope boundary | enforced: the selection is the boundary | **none** -- you are present |
| How changes land | proposal, your approval, then applied | edited directly, `ask` confirms |
| Markup guard | the range rail refuses new markers | the batch tool refuses structural markers |

Nobody is present on the document side, so its guarantees live in code; you are present in chat, so its guarantee is you. **Do not carry the "selection is the boundary" expectation into chat** — there is no selection there.
