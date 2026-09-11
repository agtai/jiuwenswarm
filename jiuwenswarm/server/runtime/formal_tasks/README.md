# Host formal Tasks and project execution

This package owns the existing durable Task service consumed by Live Voice:

- `formal_task_models.py`: admission, attempts, results and adjustment values.
- `task_store.py`: SQLite authority, outbox and recovery transactions.
- `persistent_task_core.py`: delivery and cancellation orchestration.
- `task_adjustment_queue.py`: serial durable changes and exact successor binding.
- `executor_capabilities.py`: persisted executor/profile selection.
- `project_code_executor.py`: project workspace, file effects and Agent execution.
- `file_effect_plan.py`: exact declared file operations and write fencing.

Durability receipts, checkpoints, effects and verified prefix readers belong to
`../durability`. Voice composition calls these Host services; it does not own a
second Store, database or execution engine. Relocation introduces no migration,
new scheduler, storage copy or alternate import path.

Compatibility dependencies remain explicit. The common `live_voice_contract_v2`
wire types and persisted identifiers retain their existing names and bytes.
`server/live_voice/native_task_source.py` validates the optional Native speech
evidence carried by existing Tasks; the Host must not discard that evidence or
weaken validation to make an import graph look generic. A future non-voice source
adapter needs a separately specified admission contract. This package is not an
AgentCore Goal replacement: durable effects and recovery continue to be Host-owned.

Current behavior regressions remain under `tests/unit_tests/live_voice`, notably
`test_task_adjustment_queue`, `test_authorized_project_snapshots`,
`test_file_effect_plan`, `test_project_task_handoff` and `test_persistent_task_core`.
They consume this package directly. Historical source locations are mapped in
`tests/fixtures/live_voice_retirement_manifest_v1/manifest.json`.
