# panel

The owner's side of co-scribe: what the Docs panel does when its operator adds a
document, grants or revokes a watch, connects an account, or changes a setting.

**Purpose.** `service` is the `CloudDocPanel` class, one method per `clouddoc.*`
RPC the web UI calls: listing without platform calls, add and update with a live
probe, shared-document sync, connections, watches and their usage, the audit view,
key files, mode, model and poll interval. `connections` is the connection registry:
a connection is a provider plus an account, with one watcher each, and a document
belongs to exactly one connection. `receipts_watch` watches the receipt ledger's
mtime and tells every web client when it changed. `settings` reads and writes the
deployment's `clouddoc.enabled` flag, the one switch for the whole feature.

**Public names.** `CloudDocPanel`, `CloudDocConnection`, `CloudDocConnections`,
`watch_receipts_file`, `clouddoc_enabled`, `set_clouddoc_enabled`,
`settings_payload`.

**Imports.** `providers`, `receipts`, `authority`, `state`, `watch`, `tools`,
`settings`; `jiuwenswarm.common.config` for round-trip config writes. The model-name
check and the live configuration go through `settings`. Nothing here imports the
host; the host's gateway builds the connections and the service and registers the
RPC table.
