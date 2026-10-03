# edits

The rails a write passes through before it reaches a platform. They work on the
provider's snapshot and on text, never on a client.

**Purpose.** `range_rail` turns a comment's quoted text into the window an
unattended edit may touch (exact, sentence, line or paragraph), anchors it in the
current body and refuses what falls outside; it also hands the watcher the passage a
comment sits in. `result_predicates` checks the shape of a result against the
instruction that asked for it (shorter, longer, unchanged) and refuses a definite
violation before anything is sent.

**Public names.** `RangeRailConfig`, `RangeCheck`, `check_range`, `scope_window`,
`anchor_quote`, `anchor_context`, `union_window`, `ctx_hash`, `SCOPES`;
`check_result_predicates`.

**Imports.** `providers.base` only.
