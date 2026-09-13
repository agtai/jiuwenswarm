# Single-pass local delegation — 2026-09-03

## Accepted scope before implementation

Baseline: `2d339691a13f9569c6cd41dedbecb67856da093d`. The user explicitly
requested removing the repeated model decision before local Task creation.
The previous shared-contract review repair is retained as historical evidence;
it does not establish a need for two model invocations.

Owned boundary: `task_semantics.py` and its semantic/Registry tests, Tier 2 under
root TESTING because this changes the interpretation path before Task mutation.
One valid semantic result now goes directly to existing deterministic validation
and Registry authority. Explicit contextual delegation needs no second model
approval or extra user confirmation. Foreground analysis stays dialogue;
unresolved background requests stay clarification. Original requirements and
frozen replay remain intact. This changes no public schema or authority contract.

Remove only the unconditional local-create model review, its dedicated prompt
and obsolete tests. Preserve the bounded structural retry, deadline and authority
checks; preserve the separate existing adjustment-specification check. Registry
permission, scope, capability, state, cancellation and idempotency checks remain
mandatory. No natural-language classifier, Demo exception or forced consent is
introduced. Provider/account configuration, project directory/input, result
quality, other Task operations and full Demo acceptance are excluded.

Verification will cover one-call creation with exact Store/replay truth;
foreground/clarification zero Task effects; invalid output, unowned sources,
capability denial, cancellation, timeout and bounded retry. Existing persisted
decisions retain their schema/replay; no migration, media, host-restart or broader
concurrency implementation changes are claimed. Real configured-model probes
will check the recorded delegation and a bounded cross-domain/negative set;
they cannot substitute for real microphone, Task execution or audible playback.

## Implementation and verification

The local-create review branch, prompt and unused timing/logger imports are
removed. Primary semantic instructions and all Registry/Core product code are
unchanged. Removing the review from the semantic configuration digest binds new
commits to the new behavior; persisted decision decoding is unchanged.

Product file SHA-256:
`9d763332f8ee4d160bbf6281e433eaf266d7b7456025f466755f64e1328447be`.

- **96 passed, 50 deselected** using the repository `.venv/Scripts/python.exe`:
  `-m pytest -o addopts='' -o log_cli=false
  tests/unit_tests/live_voice/test_task_semantics.py
  tests/unit_tests/live_voice/test_semantic_registry.py -q -k
  'not test_semantic_registry or explicit_local_delegation_creates_once_with_normal_authority
  or non_task_semantics_have_zero_task_effects_and_replay
  or local_delegation_requires_current_supported_executor
  or persistent_invalid_continuation_has_zero_effects_and_replays_rejection
  or unowned_requirement_source_has_zero_core_and_agent_effects
  or controlled_semantic_negative_has_zero_protected_effects
  or cascade_presented_analysis_delegation_uses_one_call_and_original_requirements
  or whole_semantic_budget_cancels_model_without_protected_effects
  or two_finals_cannot_issue_two_confirmations_from_one_proposal'`.
- **1 additional passed, 67 deselected**: the Registry module with
  `-k 'controlled_semantic_negative_has_zero_protected_effects and unknown-adjustment-target'`.
  An invalid adjustment target is rejected with unchanged Store counts, zero
  Executor dispatch/cancel/adjustment, zero Agent calls and no voice origin.
- These checks cover exact local creation/replay and preserved requirements;
  non-Task routes and invalid output with zero forbidden effects; capability and
  provenance denial, cancellation, timeout, bounded retries and competing final
  confirmations. Deterministic model fixtures do not prove language accuracy.
- The initial shell-default Python lacked repository dependencies and failed
  collection. The commands above used the existing repository environment; no
  dependency, account or Provider configuration was changed to make them pass.
- Real configured `deepseek-v4-flash#0`: the original recorded delegation and a
  non-travel contextual delegation both returned local `task.create` with **one
  model call**, preserving prior and current user requirements. No Task/Agent,
  file, audio or Registry dispatch was connected to these read-only probes.
- Retain the failed negative evidence: **6/9 expected-route checks**. Four
  foreground/quoted/hypothetical/old-delegation inputs correctly stayed dialogue.
  A constraints-only input proposed `task.adjust` despite an empty task list;
  a missing-objective delegation and a missing-task modification ended as dialogue
  instead of clarification. None proposed new creation. These observed paths do
  not enter the removed local-create review branch; primary instructions and the
  adjustment path are unchanged. They are unresolved semantic-quality defects,
  not passing acceptance cases. The invalid-target Registry check above proves
  the deterministic guard using a fixture, not a replay of the exact real output.
- Raw reports stay in the private `live-voice-demo-a0995-20260903` directory as
  `single-pass-results.json` and `single-pass.log`; failed expectations were not
  rewritten or rerun to obtain a random PASS. External-action Agent behavior is
  outside this bounded probe set and remains unaccepted.
- Main reviewed the complete scoped product/test diff and the unchanged D-109
  final authority path. No callable independent code-review tool was available;
  this is a self-review substitute, not independent review.
- Three changed Python files passed AST parsing; changed local Markdown links
  and `git diff --check` passed. The original failed Session's persisted semantic
  decision was loaded read-only and reproduced exactly, including its dialogue
  route; old committed requests are not silently reinterpreted after this repair.

The fixed verification project/input remain unchanged. Deployment is tracked by
the machine-private runtime contract. New spoken Task A, full A/B/A2, offline
ACK/refresh, physical playback and independent review remain open. Overall and
module closure remain **PARTIAL**; deleting a repeated model call does not prove
end-to-end latency or universal semantic correctness.
