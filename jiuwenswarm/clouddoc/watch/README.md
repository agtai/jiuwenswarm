# watch

The unattended path: a collaborator @-mentions the agent in a comment, and under a
live watch the agent handles that comment inside the passage the comment marks.

**Purpose.** `triggers` decides which comments and replies are a summons and which
have been consumed; `conventions` reads the collaborator-written writing rules and
acknowledges them; `texts` holds every sentence the system writes into a thread, in
the commenter's language; `turn_prompt` assembles one turn's prompt in three layers
of decreasing trust, the untrusted parts fenced with a per-turn nonce; `dispatch`
hands a turn to the agentserver on the document's own session and rotates that
session; `watcher` is the poll loop: admission, the gate, the placeholder, dispatch,
settlement and the ledger check.

**Public names.** `CloudDocCommentWatcher`, `WatcherConfig`, `CloudDocDispatcher`,
`make_cancel_fn`, `TriggerConfig`, `find_triggers`, `build_turn_prompt`,
`select_conventions`, `msg`.

**Imports.** `providers`, `edits`, `receipts`, `workmode`, `wording`, `settings`,
`state`, `authority`; `jiuwenswarm.common` for the request envelope. The model-name
check and the live configuration go through `settings`.
