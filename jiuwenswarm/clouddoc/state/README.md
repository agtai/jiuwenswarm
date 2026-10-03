# state

What the watcher keeps between polls.

**Purpose.** `store` is the per-document state file behind an asyncio lock and a
cross-process file lock: the trigger keys already consumed, the turns in flight and
their placeholder replies, the conventions acknowledged, the agentserver session
and its turn count, failure backoff, and the panel's metadata for each document.

**Public names.** `CloudDocStore`, `MAX_TRIGGERED_IDS`, `TRIGGERED_TTL_SEC`,
`BACKOFF_BASE_SEC`, `BACKOFF_MAX_SEC`.

**Imports.** `providers.kinds` for the state file location.
