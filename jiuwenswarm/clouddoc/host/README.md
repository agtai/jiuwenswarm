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
| `gateway` | the gateway's service: build the connections from the configuration, start and stop the watchers and discovery |
| `web` | the `clouddoc.*` WebSocket method table |
| `bridge` | the toolkit's tool cards as openjiuwen local functions |

Everything here is a module nothing calls yet. The wiring PR adds the calls to the
core files: the adapter holds a `CloudDocSessionTools` and calls `update` on every
request, builds the two rails into its rail table and hands `turn_snapshot` to
the permission rail; the permission rail's scene hook calls `unattended_scene`
first; the team provider's harness element calls `build_team_tools`; the gateway
prepares a `CloudDocService`, binds its panel to the web handlers through
`web.register_methods`, starts the service once the channels are up and stops
it on the way down.

**Public names.** `CloudDocFileGuardRail`, `ReportLedgerRail`, `unattended_scene`,
`resolve_unattended_turn`, `set_fallback_snapshot`, `is_unattended_turn`,
`turn_doc_id`, `turn_comment_id`, `turn_mode`, `turn_progress`,
`CloudDocSessionTools`, `build_team_tools`, `CloudDocService`, `build_connections`,
`start_discovery`, `build_methods`, `register_methods`, `to_openjiuwen`.

**Imports.** every package below; the host's rail base classes, permission table
and request contextvars; `openjiuwen` rail, tool and message types.
