# LiveVoice slimming rebaseline scripts

Read-only helpers for the incremental rebaseline required by the LiveVoice slimming master plan
(`live-voice/roadmap/LIVEVOICE_SLIMMING_MASTER_PLAN.md`). They read Git objects only, never modify
the working tree, and run from any directory inside the repository (Git paths are resolved from the
repository root). Use the shared `.venv` Python.

| Script | Purpose | Typical call |
|---|---|---|
| `symbol_delta.py` | Per-file added/removed production symbols between two revisions | `python scripts/live_voice/slimming/symbol_delta.py 59998e2c5 HEAD` |
| `inventory_loc.py` | Dedicated whole-file LOC, deleted/new production paths and shared-host drift against the atomic manifest | `python scripts/live_voice/slimming/inventory_loc.py --manifest live-voice/reviews/OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md --base 59998e2c5 --head HEAD` |
| `retire_rows.py` | Stable-symbol revalidation of manifest rows on changed paths plus importer scan of whole-file retire candidates | `python scripts/live_voice/slimming/retire_rows.py --manifest live-voice/reviews/OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md --rev HEAD --base 59998e2c5` |
| `module_buckets.py` | Coarse 18-module bucketing of dedicated LiveVoice production files with non-behaviour line share | `python scripts/live_voice/slimming/module_buckets.py --rev HEAD` |
| `anatomy_modules.py` | Per-module design anatomy (value types, owners, exceptions, guard lines, codecs) of the dedicated LiveVoice files | `python scripts/live_voice/slimming/anatomy_modules.py --rev HEAD` |
| `symbol_inventory.py` | Per-file top-level symbols with production-caller and same-file reference counts (appendix A of the design-simplification plan) | `python scripts/live_voice/slimming/symbol_inventory.py --rev HEAD --out live-voice/LIVEVOICE_DESIGN_SIMPLIFICATION_INVENTORY_2026-09-07.md` |
| `method_map.py` | Method map of the twenty giant owner classes with external-caller counts (appendix B) | `python scripts/live_voice/slimming/method_map.py --rev HEAD --out live-voice/LIVEVOICE_DESIGN_SIMPLIFICATION_METHOD_MAP_2026-09-07.md` |
| `hermes_voice_inventory.py` | Physical-LOC inventory of the official Hermes (NousResearch/hermes-agent) voice surface: curated dedicated files by category, voice-named symbol segments in shared hosts, voice test files | `python scripts/live_voice/slimming/hermes_voice_inventory.py --repo "D:/XGG AI/openjiuwen/hermes-agent-review-9a84bee26"` |

`--manifest` accepts a filesystem path (relative to the current directory or the repository root)
or `REV:PATH` for a manifest that only exists on another commit.

Known limits: static analysis only; TypeScript symbol detection covers `export` declarations;
module bucketing uses filename rules, not the manifest's per-symbol ownership; `retire_rows.py`
reads every production and test file through `git show`, so a full run takes a few minutes. A
first ad-hoc version of these scans missed `.js`-suffixed TypeScript imports and matched
`live_voice_contract` inside `_v2` names; both are fixed here.
