# authority

What a document's owner has granted, and the record of it.

**Purpose.** `watch_registry` holds one grant per document (`apply_scoped`, the
only level), with an expiry, a daily dispatch budget and a rolling-window brake. It
answers the watcher's gate at dispatch and the tools' pre-write check, issues and
revokes grants, keeps revocation tombstones so a revoked watch cannot be revived by
a stale write, and appends one line per event to the audit journal.

**Public names.** `WatchRegistry`, `WatchVerdict`, `MODES`, `RETIRED_MODES`,
`DEFAULT_WATCH_TTL_SECONDS`, `get_watch_registry_path`.

**Imports.** `settings` for the file location; nothing else from this package.
