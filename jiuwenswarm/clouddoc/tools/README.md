# tools

What the agent calls. Thirteen tools on the chat path; on an unattended turn the
closed set of four (`clouddoc_read`, `clouddoc_list_comments`,
`clouddoc_apply_for_comment`, `clouddoc_reply_comment`).

**Purpose.** `toolkit` holds `CloudDocToolkit`: one instance per session over one
provider, which resolves the document a call is about (bound by the turn on the
unattended path, named by the person on the chat path), reads bodies and remembers
what it has shown, lists and answers comments, applies bounded edits and region
writes with receipts, creates, shares and trashes documents, and reads and edits the
working-style file. `cards` renders the tool cards the host registers.

The toolkit arrives as the one module it is today; splitting it by tool group is a
later refactor, not part of the move.

**Public names.** `CloudDocToolkit`, `ALL_TOOL_NAMES`, `UNATTENDED_ALLOWLIST`,
`UNATTENDED_DENYLIST`, `UNATTENDED_FAMILIES`, `unattended_allowlist_for`,
`EFFECT_CLASSES`.

**Imports.** `providers`, `edits`, `receipts`, `workmode`, `wording`, `settings`
and, lazily for the pre-write check, `authority.watch_registry`. Nothing from the
host application.
