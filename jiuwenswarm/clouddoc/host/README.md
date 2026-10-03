# host

Where co-scribe meets the agent runtime. This is the only package allowed to
import `jiuwenswarm.server`, `jiuwenswarm.gateway`, `jiuwenswarm.agents`,
`jiuwenswarm.runtime` and `openjiuwen`; everything below it is plain Python over
the platform contract.

**Purpose.**

| Module | What it is |
|---|---|
| `file_guard` | the rail that keeps the generic file and shell tools away from co-scribe's own files and the platform CLIs, and tells the model which names are cloud documents |
| `report_ledger` | the rail that audits a turn's closing claim against the writes it made |
| `permissions` | the scene decision for an unattended turn: a tool outside the closed set is refused, not parked behind a prompt nobody can answer |
| `turn` | which turn this is, read from the request binding: unattended or not, for which document, comment and watch level |
| `agent` | the adapter's per-session state: the toolkit, the authorization snapshot, the closed-set strip, tool registration |
| `team` | the toolkit for a team member on the declarative assembly path, which refuses an unattended turn |
| `bridge` | the toolkit's tool cards as openjiuwen local functions |

Everything here is a module nothing calls yet. The wiring PR adds the calls to the
core files: the adapter holds a `CloudDocSessionTools` and calls `update` on every
request, builds the two rails into its rail table and hands `turn_snapshot` to
the permission rail; the permission rail's scene hook calls `unattended_scene`
first; the team provider's harness element calls `build_team_tools`. The gateway
service and the WebSocket method table follow in the next PR.

**Public names.** `CloudDocFileGuardRail`, `ReportLedgerRail`, `unattended_scene`,
`resolve_unattended_turn`, `set_fallback_snapshot`, `is_unattended_turn`,
`turn_doc_id`, `turn_comment_id`, `turn_mode`, `turn_progress`,
`CloudDocSessionTools`, `build_team_tools`, `to_openjiuwen`.

**Imports.** every package below; the host's rail base classes, permission table
and request contextvars; `openjiuwen` rail, tool and message types.
