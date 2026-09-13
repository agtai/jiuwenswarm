# AgentCore persistent task migration

**Goal:** Move reusable formal Task authority from JiuwenSwarm to the matching AgentCore branch, with one AgentCore commit and one consuming JiuwenSwarm commit. Work remains unchanged.

**Baseline:** JiuwenSwarm f9c8e283; AgentCore b5f189ba1054a338d8fa3e009b13053776340e44, verified ancestor of upstream/develop. Both branches are hx/0912_livevoice. No remote updates.

**Architecture:** Add `openjiuwen.core.application.tasks` as persistent delivery/attempt/outbox capability. Existing TeamTaskManager owns team assignment/dependency/review; AsyncToolRuntime owns harness background tool execution; neither replaces the exact durable command/attempt/recovery protocol. Reuse these existing execution layers where already called, without inventing a second Agent. Keep application/project authorization, model configuration, UI, speech source validation and the concrete project executor in JiuwenSwarm. The SDK has no JiuwenSwarm dependency.

**Scope and risk:** Tier 3 cross-package authority seam, behavior-preserving state/storage relocation with explicit source-evidence extension. Preserve SQLite schema version 6, serialized IDs/keys, command idempotency, authority grants, cancellation fences, source validation and recovery outcomes. No production data changes, service restart, model/provider change, UI policy change or Work migration.

## Owned boundaries and steps

- [x] Establish clone/remotes and compatible local branch; read SDK Task, async execution and checkpoint boundaries.
- [x] Extract shared task contract primitives (same class identity through host re-exports), source-evidence interface, formal models, executor capability/file-effect descriptions, persistent core/store, adjustment queue, event subscription and durability records into SDK. Remove original production implementations and update consumers.
- [x] Keep Native speech evidence codec in JiuwenSwarm; register an explicit trusted decoder and fail closed on unregistered/malformed persisted source data. Preserve original wire fields for compatibility.
- [x] Add SDK-owned standalone task/source/real-SQLite integration coverage and relocate independent durability/subscription tests. Keep Host-specific project, policy and speech journeys in JiuwenSwarm; preserve their oracles.
- [x] Exercise the new SDK through JiuwenSwarm using a local editable source, verify dependency direction and unchanged Work source, test task/store/outbox/adjustment/recovery/source and concrete project integration paths. Build packages and inspect installed import origins.
- [x] Review the complete cross-repository seam independently, resolve findings, record capability mapping, residual application adapters, counts and exact verification. Commit SDK once, record that exact SDK commit and pin its distinct local package version and record a local-source development override without publishing a nonexistent remote commit.

## Acceptance

Positive create/dispatch/complete/query and actual SQLite reopen succeed. Duplicate/stale/wrong-scope/cancel/adjust/recovery tests preserve authority and zero forbidden effects. SDK import and tests do not require JiuwenSwarm. Native source validation remains mandatory when present. No copied task kernel remains in JiuwenSwarm; thin shared-contract compatibility exports preserve existing callers. Work runtime files unchanged. Host adapter and SDK versions are explicit and reproducible locally; no claim of remote availability or physical audio acceptance.
