# providers/feishu

The Feishu / Lark implementation of the provider contract, driven through the
official `lark-cli`, always as the app (`--profile <app_id> --as bot`).

**Purpose.** `cli.py` is the seam: one class that builds, runs and classifies every
command the provider issues, with a timeout, and turns the CLI's JSON errors into
`ProviderError` kinds. `provider.py` interprets the results as documents, comments
and edits: it reads and edits the body as markdown through the CLI's own conversion,
asks the tenant at runtime what the app may do and degrades rather than fails, and
recognises the bot's own comments by its open id. `formats.py` holds the Sheets and
Slides halves.

**Public names.** `LarkCli`, `LarkResult`; `FeishuDocsProvider`; in `formats`:
`TEXT_DOMAIN` and the readers and writers the provider calls.

**Imports.** `providers.base`, `providers.textmap`, `providers.formats`; nothing
above the providers layer and nothing from the Google package.

**Platform facts the code relies on**, each measured on a tenant and noted at the
site: no document-comment event (the watcher polls), no background colour on the
write channel (replies itemise changes instead of highlighting), one command per edit
(no atomic multi-edit), quoted text truncated at 128 characters without a marker.
