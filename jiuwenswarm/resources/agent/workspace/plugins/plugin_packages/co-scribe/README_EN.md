## What you install

**Ten cloud-doc tools (natively assembled, enabled with this plugin)**:

| Tool | What it does |
|---|---|
| `clouddoc_read` | Read the full text and revision id (grids/decks include region addresses) |
| `clouddoc_list_documents` | List this connection's adopted documents |
| `clouddoc_list_comments` | List comments, with assignees and @-marks |
| `clouddoc_reply_comment` | Reply in a comment thread |
| `clouddoc_batch_edit` | Atomic batched text edits (the chat path's only write primitive) |
| `clouddoc_write_region` | Declarative region writes (move / clear / rearrange) |
| `clouddoc_apply_for_comment` | The unattended path's per-comment apply (refuses in chat) |
| `clouddoc_create_document` | Create and share (grant-class: always confirmed) |
| `clouddoc_workmode_get / edit` | Read / edit the writing conventions (receipted, revertible) |

**The mandate harness (welded into the tools, active in Mandate mode)**:

| Mechanism | What it does |
|---|---|
| Receipts | Every write records the before and after content, signed by its executor |
| Mechanical revert | One click; anchor drift refuses the whole batch -- never an approximation |
| Range & predicate rails | Comment-quote anchoring; "shorten / clear / delete X" verified mechanically before the write |
| Permission floors | Irreversible writes and grant-class actions always confirm (a code subtraction no mode can lift) |
| Read-before-write | Writes into an unread document are refused |
| The watch ladder | Off / reply-only / operate standing grants, 30-day default terms, granted−used audit |
| Unattended handling | @-assigned comments dispatch automatically, fully receipted |

**Surfaces**:

| Where | What it holds |
|---|---|
| Settings → Cloud Docs | Wiring: service-account keys, connection management |
| Docs panel | The safeguards switch (Mandate/Direct), watch grants, receipts & revert, usage audit |

**Known platform limits** (measured on live tenants; these are platform contracts, not limits of this plugin):

| Platform | Limit | What happens |
|---|---|---|
| Feishu | Comment quotes are **truncated server-side at 128 characters** with no mark (the selection highlight looks complete; the API stores only the first 128) | A selection over 128 characters cannot serve as an unattended authorization boundary and is refused with an explanation; make large-range edits from the Jiuwen chat |
| Feishu | Comments have no assignment concept | A mention triggers unattended handling (edits are confined to the one document) |
| Google | Quotes truncate around 419 characters, marked with "…" | Detectable, refused with the same guidance |

Uninstalling folds the capability away: connections, grants and the receipt ledger stay on this machine and return on reinstall.
