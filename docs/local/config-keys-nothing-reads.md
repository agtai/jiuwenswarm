# Config keys nothing reads

Surveyed 2026-08-27/28 while retiring a set of connector config keys. **Not urgent,
not acted on.** Recorded so the survey does not have to be repeated, and so that
the one item with a real consequence is not lost among the harmless ones.

Measured against the deployed tree
(`venvs/2026-08-26-full-v22/lib/python3.12/site-packages/`), counting references
in **`.py` files only** — an early count included the shipped `resources/*.yaml`
and reported three false hits.

## 1. The one that matters: a misspelled key hiding a switch that does nothing

```yaml
react.context_engine_config.session_memory_compressor_config:   # line ~350
  enabled: false
  trigger_context_ratio: 0.8
  memory:
    update_trigger_context_ratio: 0.1
```

`_resolve_session_memory_config` (`interface_deep.py:938-941`) accepts
**`session_memory_config`** or **`session_memory`**. The live config has neither
spelling — zero occurrences of each. This block has never been read.

Confirmed at runtime rather than inferred; the rail build logs it every start:

```
2026-08-28 07:30:30  session_memory=disabled
```

**Why this is worse than a dead key.** `enabled: false` matches the code default,
so nothing looks wrong and nothing warns. The block reads as a feature that was
considered and switched off. Setting it to `true` would change nothing, and the
next person to try would have no signal at all — the trap is the appearance of
control, not the loss of it.

**Not yet decided:** rename to `session_memory_config`, or delete. Renaming keeps
`enabled: false`, so it is behaviour-neutral on the day it lands and becomes a
working switch afterwards. Deleting is honest about the current state. Either
beats leaving it, and neither is urgent while the value is `false`.

## 2. Dead, harmless, zero `.py` references

| key | live value | note |
|---|---|---|
| `models.enable_free_models` | `true` | free search is env-gated (`FREE_SEARCH_DDG_ENABLED` / `FREE_SEARCH_BING_ENABLED`), never config-gated |
| `react.evolution.review_feedback_min_confidence` | `0.7` | siblings `skill_evolution` / `auto_save` do resolve, so the grep is working |
| `react.answer_chunk_size` | `500` | **also in the shipped template** |
| `react.stream_chunk_threshold` | `50` | **also in the shipped template** |
| `react.stream_character_threshold` | `2000` | **also in the shipped template** |
| `telemetry.log_messages` | `false` | **also in the shipped template** |

The four marked are orphaned **upstream**, not local drift — worth an upstream
issue rather than a local deletion, and worth knowing before someone "cleans up"
a key that upstream still ships.

## 3. Unconfirmed — a leaf-name collision, not evidence of life

These return `.py` hits, but the hits may belong to a **different dotted path**
with the same leaf. Not classified either way:

- `telemetry.provider_factory` — 2 hits, both under `extensions/external_provider/`, unrelated to telemetry config
- `progressive_tool_enabled` — 6 hits, but read off the harness config object (`deep_agent.py`), whose default is already `False`; no path maps a top-level YAML key onto it
- `react.completion_timeout` — the leaf is shared with `agents.*.completion_timeout`, which is live
- `models.agentos` — the leaf is shared with `gateway.agentos`, which is live

**Method note:** a leaf-name hit in an unrelated module is *not* evidence the key
is read. Anything settled here has to be settled on the dotted path or by finding
the actual read site.

## 4. Deliberately unread — do not delete

- `execution_guard.model_anomaly_detection_rail.*` (11 keys). The file documents
  itself: *"restored 2026-08-24: this installed build reads
  `execution_guard.llm_retry_rail`; `model_anomaly_detection_rail` below is the
  newer upstream name and is unread here."* Its **`tool_loop_compact` sub-block
  has no counterpart in the shipped template under either rail name**, so
  deleting it loses those settings with no default to fall back to.
- `react.subagent_runtime.enabled`. Zero references, but consistent with the
  staged position that this goes live when agent-core moves. Inert by design.

## Why none of this is urgent

Every item in §2 and §3 is behaviour-neutral today: the values either match the
code default or are never consulted. §1 is neutral *while it stays `false`*. The
cost is not misbehaviour but a config file that documents settings which do not
exist — which is how §1 became possible in the first place.

Related: [[config-template-prunes-unlisted-keys]] for what happens to a key the
template lacks, and [[retro-compat-for-unshipped-features]] for the neighbouring
question of which legacy paths are worth carrying at all.
