# P3 complete capability boundary evidence — 2026-08-22

## Result

**PASS for the scheduled pre-P3-9 P3 code boundary** on implementation source
`b4e70efebc1f1eb499c883566263af5275a3d48e`.

This result means the remaining P3 module decisions and product-composition code
are closed before P3-9. It does **not** pass P3-9, the cumulative human/product
Journey, complete P1/P2/P3 feature-complete acceptance, product readiness,
external telemetry operations, deployment, `develop` integration or a remote
update.

## Closed facts

| Boundary | Evidence-backed result |
|---|---|
| `provide_input` / `pause` / `resume` | Current Direct profile is formally stable zero-business-effect unsupported. `provide_input` still requires the exact current `decision_required` seam before that decision; terminal pause/resume conflicts remain truthful. |
| Executor/profile configuration | Production consumes one explicit validated Direct D0 or D2 profile. Missing, D1 and unknown values fail before Store/database construction. No D1 candidate or D1 claim exists. |
| D0/D2 truth | D0 exposes only its real dispatch/status/cancel boundary. Store-backed D2 exposes the implemented checkpoint/recovery/effect-reconciliation boundary and uses its exact persisted profile digest. |
| Durability observability | Authenticated formal status projects current outbox state, verified checkpoint/effect, linked recovery and explicit reconcile state. Recovery facts preserve producer-Attempt identity and event-head races drop diagnostics. |
| Privacy/cardinality | Python, TypeScript and the shared fixture use closed outbox/reconciliation event vocabularies. Raw/private content and credentials are absent; raw identities remain HMAC-public trace identities and never open metric labels. |
| Retirement | D-092 manifest disposition is unchanged: three prior rows remain retired and the other 18 remain retained/inventory. No generic schedule, formal Panel/route, Direct Executor, fixed media owner or consumed compatibility path was deleted. |

## Verification

All commands ran from the repository root unless a working directory is named.

1. Backend/configuration/durability/observability/retirement/AgentServer and the
   two stable-unsupported control oracles:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -o addopts= -o log_cli=false --asyncio-mode=auto -q tests/unit_tests/live_voice/test_p3_authenticated_composition.py tests/unit_tests/live_voice/test_p3_4_durability_runtime.py tests/unit_tests/live_voice/test_observability.py tests/unit_tests/live_voice/test_product_observability_runtime.py tests/unit_tests/live_voice/test_live_voice_configuration_declaration.py tests/unit_tests/live_voice/test_observability_otel_codec.py tests/unit_tests/live_voice/test_observability_correlation_contract.py tests/unit_tests/live_voice/test_product_observability_adapter.py tests/unit_tests/live_voice/test_observability_exporter.py tests/unit_tests/live_voice/test_live_voice_retirement_manifest.py tests/unit_tests/agentserver/test_live_voice_p3_route.py tests/unit_tests/live_voice/test_persistent_task_core.py::test_unimplemented_running_controls_are_durable_unsupported_zero_effects tests/unit_tests/live_voice/test_persistent_task_core.py::test_provide_input_requires_exact_current_decision_event_then_is_unsupported
   ```

   Result: **387 passed**, one existing third-party Authlib deprecation warning.

2. Registry authority/lifecycle/privacy/feature-off/failed-Journey affected set:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -o addopts= -o log_cli=false --asyncio-mode=auto -q tests/unit_tests/live_voice/test_product_composition_registry.py::test_master_flag_off_constructs_no_registry_or_adapter tests/unit_tests/live_voice/test_product_composition_registry.py::test_p2_composes_observability_worker_into_the_same_root_lease tests/unit_tests/live_voice/test_product_composition_registry.py::test_p2_real_authority_adapter_runtime_codec_backend_lifecycle tests/unit_tests/live_voice/test_product_composition_registry.py::test_diagnostic_consume_requires_one_open_session_correlation_route tests/unit_tests/live_voice/test_product_composition_registry.py::test_current_durability_diagnostics_export_every_missing_seam_without_content tests/unit_tests/live_voice/test_product_composition_registry.py::test_p2_denied_or_unavailable_authority_has_zero_downstream_effect tests/unit_tests/live_voice/test_product_composition_registry.py::test_p3_query_denied_and_mutation_have_zero_query_effect tests/unit_tests/live_voice/test_product_composition_registry.py::test_real_store_failed_journey_links_mutation_executor_generation_and_ack tests/unit_tests/live_voice/test_product_composition_registry.py::test_real_store_result_query_exports_identity_without_result_content tests/unit_tests/live_voice/test_product_composition_registry.py::test_real_store_text_projects_recovery_attempt_boundary tests/unit_tests/live_voice/test_product_composition_registry.py::test_task_intent_flag_off_has_zero_authority_or_commit_effect tests/unit_tests/live_voice/test_product_composition_registry.py::test_real_store_mutation_exports_exact_command_and_initial_outbox tests/unit_tests/live_voice/test_product_composition_registry.py::test_p3_mutation_flag_off_has_zero_composition_effect
   ```

   Result: **13 passed**.

3. Shared Python/TypeScript observability contract and feature-off checks:

   ```powershell
   npm run test:live-voice-observability
   ```

   Working directory:
   `jiuwenswarm/channels/web/frontend`.

   Result: **19 passed**.

4. Build profiles and production build:

   ```powershell
   npm run test:live-voice-build-profiles
   npm run build
   ```

   Working directory:
   `jiuwenswarm/channels/web/frontend`.

   Results: **2 passed**; production build **PASS**, 4,644 modules transformed.
   Existing Vite dynamic-import and large-chunk warnings remain non-failing.

5. Static and repository checks:

   ```powershell
   .\.venv\Scripts\python.exe -m ruff check jiuwenswarm/server/live_voice/observability.py jiuwenswarm/server/live_voice/p3_authenticated_composition.py jiuwenswarm/server/live_voice/product_composition_registry.py jiuwenswarm/server/live_voice/product_observability_runtime.py jiuwenswarm/server/live_voice/task_store.py scripts/live_voice/p3_wave2_real_evidence_producer.py scripts/live_voice/w2_rehearsal/w2_d069_runtime_diagnostic.py tests/unit_tests/live_voice/test_p3_4_durability_runtime.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py tests/unit_tests/live_voice/test_product_composition_registry.py
   .\.venv\Scripts\python.exe -m compileall -q jiuwenswarm/server/live_voice/observability.py jiuwenswarm/server/live_voice/p3_authenticated_composition.py jiuwenswarm/server/live_voice/product_composition_registry.py jiuwenswarm/server/live_voice/product_observability_runtime.py jiuwenswarm/server/live_voice/task_store.py scripts/live_voice/p3_wave2_real_evidence_producer.py scripts/live_voice/w2_rehearsal/w2_d069_runtime_diagnostic.py
   git diff --check
   ```

   Result: **PASS**.

## Independent Tier-3 review

The preliminary independent pass exposed missing shared TypeScript adjustment
outbox parity and recovery checkpoint/effect Attempt attribution; both were
corrected before the completed review. The completed independent review then
returned `C0/I2/M1`:

- use row-owned outbox delivery revision and verify canonical
  Task/Attempt/scope/executor/command-or-recovery binding;
- expose reconciliation through an explicit closed state event;
- make the new diagnostics API independently revalidate current Context.

All findings were corrected. The focused independent follow-up returned
**`C0/I0/M0`** with no remaining actionable finding. See the paired
[implementation review](../reviews/P3_COMPLETE_CAPABILITY_BOUNDARY_IMPLEMENTATION_REVIEW_2026-08-22.md).

## Remaining acceptance

P3-9 must still run the cumulative clean product Journey on an exact source.
P1/P2 latency, mounted Exit/re-enable, generation-time interruption and broader
generalization remain owned by their existing boundaries. No physical-device or
external-OTLP credit is inferred from this automated Gate.
