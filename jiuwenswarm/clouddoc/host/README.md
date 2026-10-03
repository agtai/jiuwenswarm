# host

Where co-scribe meets the agent runtime. This is the only package allowed to
import `jiuwenswarm.server`, `jiuwenswarm.gateway`, `jiuwenswarm.agents`,
`jiuwenswarm.runtime` and `openjiuwen`; everything below it is plain Python over
the platform contract.

**Purpose.** `file_guard` is the rail that keeps the generic file and shell tools
away from co-scribe's own files (the receipt ledger, the watch registry and its
journal, the state file, the keys, the working-style file) and the platform CLIs,
and that tells the model which names are cloud documents through a prompt
attachment. `report_ledger` is the rail that audits a turn's closing claim
against the writes it made. `permissions` is the scene decision for an
unattended turn: a tool outside the closed set is refused, not parked behind an
approval prompt nobody can answer. `turn` is what the decision reads when the
caller has no snapshot of its own: which turn this is, from the request binding.
`bridge` wraps the toolkit's tool cards as openjiuwen local functions.

This PR brings the rails and the scene decision in as modules. The adapter hook,
the team tool provider and the gateway service follow in the next host PR; the
wiring PR registers the rails in the rail table, calls `unattended_scene` from the
permission rail's scene hook, and installs the snapshot fallback.

**Public names.** `CloudDocFileGuardRail`, `ReportLedgerRail`, `unattended_scene`,
`resolve_unattended_turn`, `set_fallback_snapshot`, `is_unattended_turn`,
`turn_doc_id`, `turn_comment_id`, `turn_mode`, `turn_progress`, `to_openjiuwen`.

**Imports.** `providers`, `tools`; the host's rail base classes, permission table
and request contextvars; `openjiuwen` rail and message types.
