# clouddoc: co-scribe, the native cloud-document co-editing feature

Co-scribe lets the agent act as a collaborator inside shared Google and Feishu
documents, sheets and slides: attended from a chat, or unattended when a
collaborator @-mentions it in a comment, under a per-document watch the owner
grants and can revoke, with a receipt for every write.

The feature arrives in this package one module at a time, bottom-up. Until the
wiring PR lands, nothing outside the package imports it (`tests/unit_tests/clouddoc/test_dark.py`
asserts that), so each PR is inert and reviewable on its own.

| Module | Status | What it holds |
|---|---|---|
| `wording`, `settings` | landed | text normalisation; the one place below `host` that reads the deployment's configuration |
| `providers` | landed | the platform contract, the text map, shared format helpers, both platform implementations, the factory and the router |
| `edits`, `receipts`, `workmode` | landed | range and result rails, the receipt ledger, the working-style file |
| `authority`, `state` | landed | watch grants and the audit journal; the watcher's state |
| `tools` | landed | the tools the agent calls |
| `watch` | pending | the unattended path |
| `panel` | pending | the owner's operations behind the WebSocket methods |
| `host` | pending | the only module that imports the agent runtime and the gateway |

Imports go one way, bottom to top in that table; `tests/unit_tests/clouddoc/test_layering.py`
enforces it.
