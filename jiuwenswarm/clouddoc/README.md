# clouddoc: co-scribe, the native cloud-document co-editing feature

Co-scribe lets the agent act as a collaborator inside shared Google and Feishu
documents, sheets and slides: attended from a chat, or unattended when a
collaborator @-mentions it in a comment, under a per-document watch the owner
grants and can revoke, with a receipt for every write.

The package is wired into the host at five places, each a few lines in a core
file: the agent adapter holds a `host.agent.CloudDocSessionTools` and refreshes
it on every request, builds the two rails and hands the turn snapshot to the
permission rail; the permission rail's scene hook calls `host.permissions.unattended_scene`
first; the team tool provider's `swarm.clouddoc_tools` element calls
`host.team.build_team_tools`; the gateway prepares, starts and stops a
`host.gateway.CloudDocService`; the web handlers register `host.web` methods.
`clouddoc.enabled` in `config.yaml` is the switch, off by default.

| Module | What it holds |
|---|---|
| `wording`, `settings` | text normalisation; the one place below `host` that reads the deployment's configuration |
| `providers` | the platform contract, the text map, shared format helpers, both platform implementations, the factory and the router |
| `edits`, `receipts`, `workmode` | range and result rails, the receipt ledger, the working-style file |
| `authority`, `state` | watch grants and the audit journal; the watcher's state |
| `tools` | the tools the agent calls |
| `watch` | the unattended path |
| `panel` | the owner's operations behind the WebSocket methods |
| `host` | the only module that imports the agent runtime and the gateway |

Imports go one way, bottom to top in that table; `tests/unit_tests/clouddoc/test_layering.py`
enforces it.
