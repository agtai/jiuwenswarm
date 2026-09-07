# LiveVoice 巨型 owner 类的方法图（自动生成）

> 由 `scripts/live_voice/slimming/method_map.py --rev HEAD` 生成；`callers` 是其他生产文件里 `.方法名(` 的出现文件数（同名方法会高估）。

## `SqliteTaskStore`（`server/live_voice/task_store.py`，14,093 行，166 个方法，其中公开 58 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_verify_durable_lineage` | 1218 |  |  | 17 |  |
| `_outbox_from_row` | 786 |  |  | 5 |  |
| `_verify_v4_semantics` | 443 |  |  | 8 |  |
| `_verify_control_authority` | 362 |  |  | 2 |  |
| `_apply_observation` | 281 |  |  | 2 |  |
| `_verify_v5_semantics` | 273 |  |  | 7 |  |
| `create_successor` | 269 | 是 | 1 | 18 | server/live_voice/persistent_task_core.py |
| `_verify_schema_structure` | 256 |  |  | 14 |  |
| `ack_events` | 232 | 是 | 1 | 23 | server/live_voice/persistent_task_core.py |
| `recover_durable_attempt` | 230 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `_verify_business_decision_reason` | 214 |  |  | 1 |  |
| `cancel` | 213 | 是 | 69 | 50 | acp/stdio_client.py, agents/harness/common/auto_harness/scheduler.py, agents/harness/common/auto_harness/service.py |
| `_verify_v5_ack_semantics` | 208 |  |  | 3 |  |
| `retry` | 205 | 是 | 1 | 58 | server/live_voice/persistent_task_core.py |
| `_verify_decision_history` | 201 |  |  | 1 |  |
| `_decision_observed_authority` | 189 |  |  | 1 |  |
| `reprioritize` | 177 | 是 | 1 | 36 | server/live_voice/persistent_task_core.py |
| `consumer_progress_authority_page` | 177 | 是 | 0 | 0 |  |
| `_verify_decision_payload_authority` | 176 |  |  | 2 |  |
| `defer_admission` | 174 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `read_task_durability_diagnostics` | 172 | 是 | 0 | 0 |  |
| `claim_outbox` | 167 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `update` | 160 | 是 | 106 | 34 | agents/harness/common/auto_harness/issue_fix/issue_runner.py, agents/harness/common/auto_harness/issue_fix/issue_state_store.py, agents/harness/common/auto_harness/issue_fix/service.py |
| `_create_schema_v6` | 155 |  |  | 1 |  |
| `read_applied_retry_replay` | 148 | 是 | 2 | 0 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py |
| `_initialize` | 144 |  |  | 1 |  |
| `_event_authority_snapshot` | 144 |  |  | 2 |  |
| `create` | 141 | 是 | 14 | 32 | agents/harness/common/recommendation/proactive_actions.py, agents/harness/common/tools/audio_tools.py, agents/harness/common/tools/image_tools.py |
| `_decision_binding_from_row` | 138 |  |  | 2 |  |
| `_verify_v6_semantics` | 137 |  |  | 4 |  |
| `fork_durability_lineage` | 136 | 是 | 0 | 0 |  |
| `reject_outbox` | 135 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `complete_outbox` | 132 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `_decision_payload_authority` | 128 |  |  | 3 |  |
| `_verify_ack_business_decision` | 127 |  |  | 1 |  |
| `_verify_successor_admission` | 121 |  |  | 1 |  |
| `adjust` | 120 | 是 | 1 | 14 | server/live_voice/persistent_task_core.py |
| `_validate_durable_recovery` | 119 |  |  | 1 |  |
| `complete_adjustment_outbox` | 116 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `apply_observations` | 113 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `_write_adjustment_command_result` | 107 |  |  | 1 |  |
| `_settle_admission_timeout` | 105 |  |  | 2 |  |
| `append_durability_effect_fact` | 102 | 是 | 0 | 0 |  |
| `_verify_update_authority` | 99 |  |  | 2 |  |
| `resolve_lost_attempt` | 96 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `_migrate_v3_to_v4` | 87 |  |  | 3 |  |
| `_executor_observation_from_row` | 86 |  |  | 5 |  |
| `_ack_history_step` | 85 |  |  | 2 |  |
| `_verify_reprioritize_authority` | 84 |  |  | 1 |  |
| `decide_unsupported_control` | 82 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `release_outbox` | 82 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `append_durability_checkpoint` | 81 | 是 | 0 | 0 |  |
| `_append_event` | 81 |  |  | 19 |  |
| `_command_ledger_from_row` | 77 |  |  | 5 |  |
| `_migrate_v5_to_v6` | 75 |  |  | 5 |  |
| `_current_retry_authority_from_state` | 72 |  |  | 2 |  |
| `_verify_business_decision` | 72 |  |  | 10 |  |
| `_command_replay` | 71 |  |  | 9 |  |
| `_consume_durability_authorization` | 70 |  |  | 5 |  |
| `_insert_attempt` | 69 |  |  | 4 |  |
| `settle_unbound_queued_attempt` | 69 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `_settle_cancel_command_results` | 68 |  |  | 2 |  |
| `reset_expired_outbox_claims` | 68 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `list_task_read_snapshots_page` | 67 | 是 | 2 | 1 | server/live_voice/p3_production_intent_composition.py, server/live_voice/persistent_task_core.py |
| `_verify_v4_lineage` | 65 |  |  | 8 |  |
| `_migrate_v4_to_v5` | 64 |  |  | 4 |  |
| `_ack_lacked_legacy_adoption` | 63 |  |  | 1 |  |
| `unread_events_page` | 62 | 是 | 1 | 1 | server/live_voice/persistent_task_core.py |
| `_settle_cancel_before_dispatch` | 61 |  |  | 2 |  |
| `list_tasks_page` | 61 | 是 | 1 | 0 | server/live_voice/p3_authenticated_composition.py |
| `_current_durable_recovery_authority` | 59 |  |  | 2 |  |
| `mark_reconciliation_pending` | 55 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `_persist_business_decision` | 54 |  |  | 21 |  |
| `_retry_authority_from_connection` | 53 |  |  | 2 |  |
| `_reject_open_adjustments_before_terminal` | 51 |  |  | 5 |  |
| `claim_durability_mutator` | 50 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `renew_outbox_claim` | 50 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `mark_reconciliation_resolved` | 50 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `_require_recovery_effect_safety` | 49 |  |  | 2 |  |
| `read_durable_recovery_dispatch` | 48 | 是 | 1 | 0 | server/live_voice/project_code_executor.py |
| `_events` | 48 |  |  | 2 |  |
| `_business_decision_fingerprint` | 47 |  |  | 1 |  |
| `_insert_outbox` | 47 |  |  | 6 |  |
| `_require_effect_continuation` | 45 |  |  | 1 |  |
| `events_page` | 45 | 是 | 2 | 0 | server/live_voice/p3_production_intent_composition.py, server/live_voice/persistent_task_core.py |
| `_durability_binding_from_connection` | 44 |  |  | 14 |  |
| `_verified_retry_replay` | 44 |  |  | 2 |  |
| `_verify_legacy_candidate_v6_recovery_fence` | 43 |  |  | 1 |  |
| `_legacy_consumption_anchor_v1` | 43 |  |  | 3 |  |
| `_insert_event` | 43 |  |  | 5 |  |
| `_profile_binding_from_selection` | 41 |  |  | 1 |  |
| `_control_command_from_row` | 41 |  |  | 10 |  |
| `_task_read_snapshot_from_rows` | 41 |  |  | 3 |  |
| `nonterminal_attempts` | 40 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `_migrate_v1_to_v2` | 38 |  |  | 1 |  |
| `_mark_admission_reconciliation_required` | 38 |  |  | 5 |  |
| `_finalize_adjustment` | 38 |  |  | 2 |  |
| `_migrate_v2_to_v3` | 36 |  |  | 2 |  |
| `get_current_background_task` | 35 | 是 | 0 | 0 |  |
| `_is_exact_unbound_queue` | 35 |  |  | 2 |  |
| `_require_admission_row` | 34 |  |  | 2 |  |
| `_validate_successor_command` | 33 |  |  | 1 |  |
| `read_retry_authority` | 31 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `read_current_retry_authority` | 31 | 是 | 2 | 0 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py |
| `_task_result_for_row` | 31 |  |  | 2 |  |
| `_task_from_row` | 29 |  |  | 14 |  |
| `_v5_consumer_rows` | 27 |  |  | 3 |  |
| `_outbox_payload` | 27 |  |  | 6 |  |
| `_task_result_from_row` | 27 |  |  | 6 |  |
| `_event_from_row` | 27 |  |  | 9 |  |
| `read_durability_checkpoints` | 26 | 是 | 2 | 0 | server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py |
| `read_durability_effects` | 26 | 是 | 2 | 0 | server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py |
| `_mutation_result` | 26 |  |  | 15 |  |
| `_verify_metadata_schema` | 25 |  |  | 1 |  |
| `_normalize_legacy_candidate_v6` | 25 |  |  | 1 |  |
| `_task_read_attempt_row` | 25 |  |  | 3 |  |
| `_insert_command` | 24 |  |  | 10 |  |
| `_business_decisions_for_type` | 23 |  |  | 1 |  |
| `_require_consumer_task_row` | 23 |  |  | 7 |  |
| `_connect` | 22 |  |  | 5 |  |
| `_snapshot_reader` | 22 |  |  | 12 |  |
| `_require_mutation_precondition` | 22 |  |  | 2 |  |
| `_mutation_fingerprint` | 22 |  |  | 4 |  |
| `_transaction` | 20 |  |  | 29 |  |
| `_checkpoint_rows` | 20 |  |  | 3 |  |
| `_effect_rows` | 20 |  |  | 4 |  |
| `_retry_state_from_connection` | 20 |  |  | 4 |  |
| `_is_durable_retry_business_error` | 19 |  |  | 2 |  |
| `read_durable_recovery_authority` | 19 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `release_durability_mutator` | 18 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `_ack_result_types_exact` | 18 |  |  | 3 |  |
| `_verified_checkpoint_prefix` | 17 |  |  | 12 |  |
| `_verified_effect_prefix` | 17 |  |  | 12 |  |
| `consumer_events` | 17 | 是 | 0 | 0 |  |
| `_attempt_from_row` | 17 |  |  | 9 |  |
| `read_durability_binding` | 16 | 是 | 2 | 0 | server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py |
| `_enable_wal_journal_mode` | 15 |  |  | 1 |  |
| `events` | 15 | 是 | 5 | 41 | agents/harness/team/handlers/base_monitor_handler.py, agents/harness/team/handlers/team_monitor_handler.py, server/live_voice/jiuwenswarm_agent_adapter.py |
| `counts` | 15 | 是 | 0 | 0 |  |
| `_require_task_row` | 15 |  |  | 30 |  |
| `_verify_database` | 14 |  |  | 12 |  |
| `has_pending_adjustments` | 14 | 是 | 0 | 0 |  |
| `_mutation_precondition_from_fingerprint` | 13 |  |  | 2 |  |
| `_reader` | 12 |  |  | 15 |  |
| `_creation_fingerprint` | 12 |  |  | 2 |  |
| `_retry_fingerprint` | 12 |  |  | 3 |  |
| `get_attempt` | 12 | 是 | 1 | 0 | server/live_voice/p3_authenticated_composition.py |
| `_require_task_row_by_id` | 12 |  |  | 26 |  |
| `consumer_event_authority_snapshot` | 11 | 是 | 0 | 0 |  |
| `__init__` | 10 |  |  | 0 |  |
| `admission_projection` | 10 | 是 | 0 | 0 |  |
| `_mutation_precondition_stale` | 9 |  |  | 2 |  |
| `event_authority_snapshot` | 9 | 是 | 0 | 1 |  |
| `task_result` | 8 | 是 | 2 | 0 | server/live_voice/p3_production_intent_composition.py, server/live_voice/persistent_task_core.py |
| `consumer_task_result` | 8 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `task_read_snapshot` | 8 | 是 | 3 | 1 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py |
| `get_consumer_task` | 7 | 是 | 1 | 0 | server/live_voice/persistent_task_core.py |
| `list_tasks` | 7 | 是 | 3 | 0 | agents/harness/common/auto_harness/service.py, server/live_voice/p3_authenticated_composition.py, server/runtime/skill/skilldev/service.py |
| `_schema_unsupported` | 6 |  |  | 23 |  |
| `_corrupt` | 6 |  |  | 212 |  |
| `_is_lower_sha256` | 6 |  |  | 3 |  |
| `get_task` | 5 | 是 | 9 | 0 | agents/harness/common/auto_harness/issue_fix/service.py, agents/harness/common/auto_harness/scheduler.py, agents/harness/common/auto_harness/service.py |
| `_effect_actor` | 4 |  |  | 1 |  |
| `_hit` | 3 |  |  | 83 |  |
| `_sha256_hex` | 2 |  |  | 6 |  |
| `_json_value_sha256` | 2 |  |  | 23 |  |

## `AgentServerProductCompositionRegistry`（`server/live_voice/product_composition_registry.py`，15,059 行，184 个方法，其中公开 27 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_run_p3_production_intent` | 664 |  |  | 2 |  |
| `handle_p3_progress_activate` | 611 | 是 | 1 | 0 | server/agent_ws_server.py |
| `handle_p2_activate` | 584 | 是 | 1 | 0 | server/agent_ws_server.py |
| `_handle_p3_query_locked` | 558 |  |  | 1 |  |
| `handle_native_propose` | 547 | 是 | 1 | 0 | server/agent_ws_server.py |
| `handle_p3_progress_ack` | 513 | 是 | 1 | 0 | server/agent_ws_server.py |
| `handle_unified_submit` | 512 | 是 | 1 | 0 | server/agent_ws_server.py |
| `_run_unified_submit_decided` | 480 |  |  | 1 |  |
| `handle_native_presentation_ack` | 334 | 是 | 1 | 0 | server/agent_ws_server.py |
| `handle_p2_presentation_failed` | 314 | 是 | 1 | 0 | server/agent_ws_server.py |
| `_emit_voice_progress` | 284 |  |  | 2 |  |
| `handle_p2_presentation_ack` | 268 | 是 | 1 | 0 | server/agent_ws_server.py |
| `__init__` | 257 |  |  | 5 |  |
| `_run_native_delegate_propose` | 254 |  |  | 1 |  |
| `_emit_text_progress` | 222 |  |  | 6 |  |
| `_prepare_progress_presentation` | 209 |  |  | 2 |  |
| `handle_p2_close` | 206 | 是 | 1 | 0 | server/agent_ws_server.py |
| `handle_p3_intent` | 204 | 是 | 1 | 0 | server/agent_ws_server.py |
| `handle_p2_interrupt_generation` | 188 | 是 | 1 | 0 | server/agent_ws_server.py |
| `_verified_result_artifact_snapshots` | 185 |  |  | 1 |  |
| `handle_p3_progress_close` | 175 | 是 | 1 | 0 | server/agent_ws_server.py |
| `handle_native_close` | 174 | 是 | 1 | 0 | server/agent_ws_server.py |
| `_bounded_untrusted_result_context` | 170 |  |  | 2 |  |
| `_acknowledge_task_voice_presentation` | 169 |  |  | 1 |  |
| `handle_p3_intent_status` | 165 | 是 | 1 | 0 | server/agent_ws_server.py |
| `handle_p2_notification_next` | 160 | 是 | 1 | 0 | server/agent_ws_server.py |
| `handle_p2_barge_in` | 155 | 是 | 1 | 0 | server/agent_ws_server.py |
| `_validate_task_intent_params` | 153 |  |  | 1 |  |
| `_run_p3_mutation` | 145 |  |  | 1 |  |
| `_dispatch_semantic_agent_turn` | 133 |  |  | 1 |  |
| `_present_unified_text` | 132 |  |  | 1 |  |
| `_next_p2_notification` | 130 |  |  | 1 |  |
| `_issue_production_confirmation_continuation` | 125 |  |  | 2 |  |
| `_confirm_production_intent` | 122 |  |  | 1 |  |
| `_consume_product_observability_fact` | 112 |  |  | 2 |  |
| `_run_unified_agent_submit` | 110 |  |  | 1 |  |
| `handle_p3_mutation` | 110 | 是 | 1 | 0 | server/agent_ws_server.py |
| `_emit_authoritative_route_diagnostic` | 107 |  |  | 10 |  |
| `_handle_native_delegate_propose` | 107 |  |  | 1 |  |
| `_retain_production_continuation` | 105 |  |  | 2 |  |
| `close_active_routes` | 105 | 是 | 1 | 1 | server/agent_ws_server.py |
| `_run_native_close` | 101 |  |  | 1 |  |
| `handle_p3_confirmation_issue` | 100 | 是 | 1 | 0 | server/agent_ws_server.py |
| `_recover_unified_authoritative_presentation` | 93 |  |  | 1 |  |
| `_validate_product_p3_mutation_params` | 93 |  |  | 2 |  |
| `_emit_authoritative_status_diagnostics` | 84 |  |  | 1 |  |
| `_run_p3_confirmation_issue` | 84 |  |  | 1 |  |
| `stop` | 82 | 是 | 16 | 4 | agents/harness/common/auto_harness/service.py, agents/harness/common/memory/dreaming/__init__.py, agents/harness/common/memory/manager.py |
| `_authority_registration` | 80 |  |  | 14 |  |
| `_emit_authoritative_progress_generation` | 79 |  |  | 2 |  |
| `_deliver_terminal_notification` | 79 |  |  | 2 |  |
| `_gateway_voice_provenance` | 79 |  |  | 1 |  |
| `_run_unified_foreground_effect` | 79 |  |  | 2 |  |
| `_reserve_turn_commit_locked` | 75 |  |  | 0 |  |
| `_obtain_task_intent_commit` | 73 |  |  | 1 |  |
| `_emit_authoritative_task_event` | 70 |  |  | 1 |  |
| `_next_p2_response_generation` | 64 |  |  | 1 |  |
| `_settle_cancelled_unified_submit` | 64 |  |  | 1 |  |
| `_content_free_intent_recovery` | 64 |  |  | 1 |  |
| `_serialize_p2_notification` | 61 |  |  | 1 |  |
| `_remember_terminal_notifications_for_p2_route` | 58 |  |  | 6 |  |
| `_restore_voice_task_origins` | 58 |  |  | 2 |  |
| `_validated_task_result_context_parts` | 58 |  |  | 3 |  |
| `_begin_dialogue_speculation` | 58 |  |  | 1 |  |
| `_run_unified_submit` | 58 |  |  | 2 |  |
| `_guard_committed_input_locked` | 57 |  |  | 2 |  |
| `_terminal_notification_text` | 56 |  |  | 1 |  |
| `_defer_voice_progress` | 51 |  |  | 1 |  |
| `_resolve_clarification_selection` | 51 |  |  | 1 |  |
| `_preflight_p3_production_intent` | 50 |  |  | 1 |  |
| `_resolve_semantic_input` | 48 |  |  | 2 |  |
| `_create_p2_runtime` | 46 |  |  | 1 |  |
| `_base_registrations` | 46 |  |  | 3 |  |
| `_require_p2_binding_authority_locked` | 46 |  |  | 8 |  |
| `_defer_progress_presentation` | 44 |  |  | 3 |  |
| `_task_progress_foreground_supplier` | 44 |  |  | 1 |  |
| `_settle_consumed_task_presentation` | 43 |  |  | 2 |  |
| `_evict_completed_product_operation` | 43 |  |  | 15 |  |
| `_production_intent_continuation` | 43 |  |  | 1 |  |
| `_preflight_p3_mutation` | 42 |  |  | 1 |  |
| `_observe_p2_activation` | 40 |  |  | 1 |  |
| `_parse_p2_route_binding` | 39 |  |  | 6 |  |
| `_critical_input_provenance_locked` | 39 |  |  | 2 |  |
| `_record_closed_task_presentation` | 38 |  |  | 4 |  |
| `_peek_production_intent_continuation` | 38 |  |  | 1 |  |
| `_emit_authoritative_progress_ack` | 37 |  |  | 3 |  |
| `_parse_supersedes_response` | 37 |  |  | 1 |  |
| `_reserve_voice_origin_mutation_locked` | 37 |  |  | 1 |  |
| `_drain_progress_presentation` | 36 |  |  | 3 |  |
| `_drain_voice_progress_for_p2_binding` | 36 |  |  | 2 |  |
| `_close_task_presentations_for_p2_route` | 36 |  |  | 4 |  |
| `_archive_progress_route` | 35 |  |  | 4 |  |
| `_intent_rejected_result` | 35 |  |  | 9 |  |
| `_drain_root_cleanup` | 34 |  |  | 1 |  |
| `_close_task_presentations_for_progress_route` | 34 |  |  | 4 |  |
| `_production_intent_request` | 34 |  |  | 1 |  |
| `_reauthorize_task_presentation_replay` | 32 |  |  | 2 |  |
| `_persist_or_retain_native_assistant_history` | 32 |  |  | 2 |  |
| `_reserve_task_result_context_slot` | 32 |  |  | 2 |  |
| `_formal_receipt_measurement_identity` | 32 |  |  | 1 |  |
| `_admit_progress_generation_key` | 31 |  |  | 1 |  |
| `_start_text_progress_fallback` | 30 |  |  | 1 |  |
| `_require_active_p2_route_locked` | 29 |  |  | 6 |  |
| `_drop_voice_task_origins_for_route_locked` | 29 |  |  | 4 |  |
| `_task_presentation_ack_command_id` | 28 |  |  | 2 |  |
| `_native_gateway_descriptor` | 27 |  |  | 2 |  |
| `_classify_production_task_intent` | 27 |  |  | 2 |  |
| `_retain_closed_progress_route` | 26 |  |  | 1 |  |
| `_retain_terminal_after_voice_owner_loss` | 26 |  |  | 2 |  |
| `_task_result_context_entries` | 26 |  |  | 1 |  |
| `_schedule_progress_presentation_drain` | 25 |  |  | 1 |  |
| `consume_product_observation` | 24 | 是 | 0 | 3 |  |
| `_reserve_progress_delivery` | 24 |  |  | 2 |  |
| `_advance_notification_replay_floor` | 24 |  |  | 1 |  |
| `_release_native_assistant_history_after_user` | 24 |  |  | 1 |  |
| `_require_voice_origin` | 24 |  |  | 2 |  |
| `_invoke_production_resolution` | 24 |  |  | 2 |  |
| `_activate_observability` | 23 |  |  | 1 |  |
| `_preflight_turn_commit_identity_locked` | 23 |  |  | 1 |  |
| `handle_p3_query` | 23 | 是 | 1 | 0 | server/agent_ws_server.py |
| `_peek_voice_task_intent_commit` | 23 |  |  | 1 |  |
| `_require_create_receipt` | 23 |  |  | 2 |  |
| `_retain_presented_semantic_analysis` | 21 |  |  | 1 |  |
| `_production_voice_origin` | 21 |  |  | 1 |  |
| `_exact_voice_task_presentation_route` | 20 |  |  | 3 |  |
| `_task_presentation_runtime_authority` | 20 |  |  | 1 |  |
| `_retain_consumed_task_presentation_ack` | 20 |  |  | 1 |  |
| `_release_completed_unified_identity` | 20 |  |  | 9 |  |
| `_release_failed_production_intent` | 20 |  |  | 2 |  |
| `_native_assistant_history_projection` | 19 |  |  | 2 |  |
| `consume_product_metric` | 18 | 是 | 0 | 0 |  |
| `_current_observability_correlation` | 18 |  |  | 1 |  |
| `_release_voice_origin_locked` | 18 |  |  | 2 |  |
| `_preflight_p3_confirmation_issue` | 18 |  |  | 1 |  |
| `_production_resolution_facts` | 18 |  |  | 5 |  |
| `_remember_terminal_notification` | 17 |  |  | 4 |  |
| `_terminal_text_event` | 17 |  |  | 3 |  |
| `_release_task_intent_commit_locked` | 17 |  |  | 8 |  |
| `_release_production_intent_origins` | 17 |  |  | 7 |  |
| `_route_context` | 16 |  |  | 7 |  |
| `_require_turn_commit_not_retired_locked` | 16 |  |  | 1 |  |
| `_capture_semantic_analysis` | 16 |  |  | 4 |  |
| `_native_delegate_speech_text` | 16 |  |  | 1 |  |
| `_promote_orphaned_terminal_notifications` | 15 |  |  | 1 |  |
| `_current_task_presentation_route` | 15 |  |  | 3 |  |
| `handle_p2_submit` | 15 | 是 | 1 | 0 | server/agent_ws_server.py |
| `_require_product_request_not_evicted` | 14 |  |  | 11 |  |
| `_p2_keepalive` | 14 |  |  | 1 |  |
| `_record_p2_response_generation` | 13 |  |  | 3 |  |
| `_p2_response_generation_high_water` | 13 |  |  | 1 |  |
| `_current_terminal_notification_route` | 13 |  |  | 1 |  |
| `_acknowledge_terminal_notification` | 13 |  |  | 1 |  |
| `_evicted_product_request_indices` | 13 |  |  | 3 |  |
| `_retire_prior_production_continuation` | 13 |  |  | 2 |  |
| `_p2_response_generation_indices` | 12 |  |  | 2 |  |
| `_retain_closed_p2_route` | 12 |  |  | 4 |  |
| `_closed_p2_generation_indices` | 12 |  |  | 2 |  |
| `_record_closed_p2_generation` | 12 |  |  | 1 |  |
| `_retire_p2_root_cleanup` | 11 |  |  | 2 |  |
| `_task_progress_presentable` | 11 |  |  | 7 |  |
| `_preserve_orphaned_terminal_for_progress_route` | 11 |  |  | 3 |  |
| `_p2_notification_can_precede_another` | 11 |  |  | 1 |  |
| `_bind_p2_notification` | 11 |  |  | 2 |  |
| `_media_unavailable` | 10 |  |  | 1 |  |
| `_control_unavailable` | 10 |  |  | 1 |  |
| `_closed_p2_generation_high_water` | 9 |  |  | 1 |  |
| `_diagnostic_route` | 8 |  |  | 3 |  |
| `_generation_is_current` | 8 |  |  | 1 |  |
| `_registration` | 8 |  |  | 7 |  |
| `_issue_observability_route_fact` | 8 |  |  | 1 |  |
| `_p3_control_manifest` | 8 |  |  | 14 |  |
| `_progress_key_for_delivery` | 7 |  |  | 4 |  |
| `_ensure_running` | 7 |  |  | 20 |  |
| `_consume_voice_origin_locked` | 7 |  |  | 1 |  |
| `_p3_control_ready` | 7 |  |  | 6 |  |
| `_retain_root_cleanup` | 5 |  |  | 8 |  |
| `_settle_progress_route_adoption` | 4 |  |  | 5 |  |
| `_task_notification_subject` | 4 |  |  | 2 |  |
| `_retire_voice_origin_locked` | 4 |  |  | 3 |  |
| `_mark_evicted_product_request` | 3 |  |  | 6 |  |
| `p3_text_enabled` | 2 | 是 | 0 | 12 |  |
| `p2_enabled` | 2 | 是 | 0 | 14 |  |
| `p3_mutation_enabled` | 2 | 是 | 0 | 6 |  |
| `_is_chinese_voice_text` | 2 |  |  | 3 |  |

## `DedicatedMediaProductRegistry`（`gateway/live_voice/dedicated_media_registration.py`，6,726 行，123 个方法，其中公开 55 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `observe_agent_response` | 376 | 是 | 1 | 1 | gateway/channel_manager/web/web_connect.py |
| `activate` | 332 | 是 | 3 | 3 | server/live_voice/product_composition_registry.py, server/live_voice/product_composition_root.py, server/live_voice/product_p3_text_adapter.py |
| `_allocate_native_downlink` | 280 |  |  | 3 |  |
| `_try_streaming_synthesis_admitted` | 267 |  |  | 1 |  |
| `acknowledge_native_playout` | 264 | 是 | 0 | 1 |  |
| `_queue_native_user_transcript` | 217 |  |  | 1 |  |
| `acknowledge_playout` | 211 | 是 | 0 | 1 |  |
| `authorize` | 176 | 是 | 5 | 3 | server/live_voice/batch_speech.py, server/live_voice/persistent_task_core.py, server/live_voice/task_event_subscription.py |
| `streaming_recognition_result` | 170 | 是 | 0 | 1 |  |
| `prepare_synthesis_downlink` | 170 | 是 | 0 | 0 |  |
| `_build_streaming_observability` | 147 |  |  | 1 |  |
| `_run_native_session_close` | 124 |  |  | 1 |  |
| `revoke` | 112 | 是 | 1 | 6 | server/live_voice/streaming_speech.py |
| `_observe_streaming_outcome` | 109 |  |  | 1 |  |
| `_handle_native_event` | 107 |  |  | 7 |  |
| `complete_downlink` | 105 | 是 | 0 | 1 |  |
| `_return_native_delegate_result` | 104 |  |  | 1 |  |
| `finish_streaming_recognition` | 102 | 是 | 0 | 1 |  |
| `take_native_notification_response` | 95 | 是 | 0 | 0 |  |
| `_admit_streaming_synthesis` | 95 |  |  | 2 |  |
| `__init__` | 94 |  |  | 4 |  |
| `accept_native_playback_stop` | 93 | 是 | 0 | 2 |  |
| `start_streaming_recognition` | 82 | 是 | 0 | 3 |  |
| `_open_streaming_recognition` | 72 |  |  | 1 |  |
| `_run_native_delivery` | 69 |  |  | 1 |  |
| `stop_native_playout` | 69 | 是 | 0 | 1 |  |
| `mark_native_notification_forwarded` | 68 | 是 | 0 | 0 |  |
| `_task_preparation_request` | 65 |  |  | 4 |  |
| `accept_native_frame` | 64 | 是 | 0 | 1 |  |
| `_deliver_native_audio_batch` | 64 |  |  | 1 |  |
| `wait_streaming_end_of_turn` | 63 | 是 | 0 | 1 |  |
| `prepare_task_notification` | 62 | 是 | 0 | 1 |  |
| `_admit_native_response` | 61 |  |  | 1 |  |
| `complete_route` | 61 | 是 | 0 | 1 |  |
| `_run_native_events` | 60 |  |  | 1 |  |
| `_observe_task_presentation_failure` | 59 |  |  | 1 |  |
| `_run_native_session_start` | 57 |  |  | 1 |  |
| `begin_native_interaction` | 52 | 是 | 0 | 1 |  |
| `observe_uplink_ack_sent` | 51 | 是 | 0 | 1 |  |
| `_prune` | 48 |  |  | 17 |  |
| `_seal_native_downlink` | 47 |  |  | 1 |  |
| `wait_streaming_speech_start` | 47 | 是 | 0 | 1 |  |
| `_revoke_media_for_product_activation` | 46 |  |  | 5 |  |
| `consume_ticket` | 44 | 是 | 0 | 1 |  |
| `claim_task_notification` | 44 | 是 | 0 | 1 |  |
| `_native_request_state` | 42 |  |  | 6 |  |
| `prepare_streaming_provider` | 42 | 是 | 0 | 1 |  |
| `context_for` | 41 | 是 | 0 | 0 |  |
| `read_native_text` | 40 | 是 | 0 | 1 |  |
| `_require_native_start_owner` | 39 |  |  | 8 |  |
| `_retain_native_start` | 37 |  |  | 1 |  |
| `_read_native_business_context` | 36 |  |  | 2 |  |
| `_retain_synthesis_transfer` | 36 |  |  | 1 |  |
| `_publish_native_work_state` | 35 |  |  | 2 |  |
| `accept_streaming_frame` | 35 | 是 | 0 | 1 |  |
| `_schedule_streaming_abort` | 35 |  |  | 3 |  |
| `close_native_interaction` | 33 | 是 | 0 | 4 |  |
| `_retain_native_end_of_turn` | 33 |  |  | 1 |  |
| `_consume_native_task` | 31 |  |  | 2 |  |
| `observe_uplink_frame_accepted` | 31 | 是 | 0 | 1 |  |
| `_retain_native_speech_start` | 30 |  |  | 1 |  |
| `try_streaming_synthesis` | 30 | 是 | 1 | 0 | gateway/channel_manager/web/app_web_handlers.py |
| `wait_native_speech_start` | 29 | 是 | 0 | 1 |  |
| `_native_barge_action_id` | 29 |  |  | 1 |  |
| `wait_native_end_of_turn` | 28 | 是 | 0 | 1 |  |
| `_schedule_native_close` | 28 |  |  | 5 |  |
| `_deliver_native_audio` | 27 |  |  | 2 |  |
| `_emit_streaming_observability` | 27 |  |  | 4 |  |
| `abort_native_activation` | 26 | 是 | 0 | 0 |  |
| `_await_streaming_begin` | 26 |  |  | 2 |  |
| `_run_native_delegate_event` | 23 |  |  | 1 |  |
| `take_native_notification` | 22 | 是 | 0 | 0 |  |
| `configure_streaming_synthesis` | 22 | 是 | 1 | 0 | gateway/channel_manager/web/app_web_handlers.py |
| `_streaming_fallback` | 22 |  |  | 19 |  |
| `_log_first_frame_diagnostic` | 22 |  |  | 2 |  |
| `mark_downlink_started` | 22 | 是 | 0 | 1 |  |
| `from_environment` | 20 | 是 | 2 | 0 | gateway/channel_manager/web/app_web_handlers.py, server/live_voice/product_composition_registry.py |
| `_native_work_state_rows` | 20 |  |  | 2 |  |
| `next_native_notification` | 19 | 是 | 0 | 0 |  |
| `_profile_native_business_context` | 19 |  |  | 2 |  |
| `_reconcile_task_preparations` | 19 |  |  | 13 |  |
| `_settle_streaming_begin` | 18 |  |  | 3 |  |
| `_live_native_task_synthesis` | 18 |  |  | 2 |  |
| `_has_retained_product_activation` | 18 |  |  | 21 |  |
| `_native_stop_response` | 17 |  |  | 3 |  |
| `configure_streaming_recognition` | 17 | 是 | 1 | 0 | gateway/channel_manager/web/app_web_handlers.py |
| `accept_frame` | 17 | 是 | 0 | 1 |  |
| `_media_capacity_in_use` | 17 |  |  | 5 |  |
| `_retain_native_playout_replay` | 16 |  |  | 1 |  |
| `_native_task_presentation_busy` | 15 |  |  | 1 |  |
| `_first_frame_scope_sha256` | 15 |  |  | 1 |  |
| `_refresh_native_business_context` | 14 |  |  | 2 |  |
| `_release_stream_source` | 13 |  |  | 12 |  |
| `abort_streaming_recognition` | 13 | 是 | 0 | 3 |  |
| `_run_native_business_poll` | 12 |  |  | 1 |  |
| `_retain_native_barge_fence` | 12 |  |  | 2 |  |
| `_native_request_id` | 12 |  |  | 13 |  |
| `abort_route` | 12 | 是 | 0 | 1 |  |
| `_fence_native_start` | 11 |  |  | 2 |  |
| `_retain_streaming_outcome` | 11 |  |  | 15 |  |
| `_remember_revoked` | 11 |  |  | 3 |  |
| `_native_session_key` | 10 |  |  | 3 |  |
| `_streaming_capture_current` | 10 |  |  | 1 |  |
| `cancel_task_notification` | 10 | 是 | 0 | 1 |  |
| `_run_native_input` | 9 |  |  | 1 |  |
| `_native_playout_request_sha256` | 9 |  |  | 2 |  |
| `_prune_synthesis_transfers` | 9 |  |  | 3 |  |
| `close_streaming_diagnostics` | 8 | 是 | 0 | 0 |  |
| `_schedule_streaming_outcome` | 8 |  |  | 1 |  |
| `begin_streaming_recognition` | 8 | 是 | 0 | 0 |  |
| `_revise_native_text` | 8 |  |  | 5 |  |
| `task_preparation_capabilities` | 7 | 是 | 0 | 1 |  |
| `_consume_stream_cleanup` | 6 |  |  | 1 |  |
| `_native_response_is_barge_fenced` | 5 |  |  | 14 |  |
| `native_runtime_client` | 4 | 是 | 0 | 5 |  |
| `close_streaming_observability` | 4 | 是 | 0 | 0 |  |
| `retry_media_leaf_cleanup` | 4 | 是 | 0 | 0 |  |
| `close_media_leaf_cleanup` | 4 | 是 | 0 | 0 |  |
| `_drop_pending_for_record_id` | 4 |  |  | 9 |  |
| `streaming_observability` | 2 | 是 | 0 | 7 |  |
| `media_leaf_cleanup_snapshot` | 2 | 是 | 0 | 1 |  |
| `set_provider_available` | 2 | 是 | 1 | 0 | gateway/channel_manager/web/app_web_handlers.py |
| `streaming_diagnostics_cleanup_complete` | 2 | 是 | 0 | 0 |  |

## `DirectProjectCodeExecutorAdapter`（`server/live_voice/project_code_executor.py`，3,438 行，52 个方法，其中公开 19 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_run_attempt` | 470 |  |  | 1 |  |
| `_resume_d2_recovery` | 421 |  |  | 1 |  |
| `_dispatch` | 230 |  |  | 1 |  |
| `reconcile_durable_effects` | 186 | 是 | 0 | 0 |  |
| `authorize_durable_recovery` | 171 | 是 | 0 | 0 |  |
| `_consume_adjustment_checkpoint` | 149 |  |  | 1 |  |
| `_prepare_d2_project_effect` | 115 |  |  | 1 |  |
| `close` | 97 | 是 | 0 | 13 |  |
| `recovery_facts` | 96 | 是 | 0 | 1 |  |
| `retry_readiness` | 95 | 是 | 0 | 0 |  |
| `cancel` | 87 | 是 | 68 | 16 | acp/stdio_client.py, agents/harness/common/auto_harness/scheduler.py, agents/harness/common/auto_harness/service.py |
| `__init__` | 83 |  |  | 5 |  |
| `prepare_startup` | 78 | 是 | 1 | 0 | server/live_voice/p3_authenticated_composition.py |
| `_delivery` | 73 |  |  | 15 |  |
| `_mutation_authorization` | 66 |  |  | 3 |  |
| `_settle_d2_project_effect` | 64 |  |  | 1 |  |
| `_parsed_selection` | 54 |  |  | 4 |  |
| `_fork_recovery_lineage` | 53 |  |  | 1 |  |
| `_adopt_model_adjustments` | 52 |  |  | 2 |  |
| `_append_effect_bound_checkpoint` | 50 |  |  | 4 |  |
| `adjust` | 50 | 是 | 1 | 10 | server/live_voice/persistent_task_core.py |
| `_heartbeat` | 49 |  |  | 1 |  |
| `_cleanup_attempt_resources` | 49 |  |  | 1 |  |
| `status` | 47 | 是 | 11 | 20 | agents/harness/common/memory_rpc.py, agents/harness/common/tools/memory_tools.py, gateway/channel_manager/web/app_web_handlers.py |
| `_observe_stream_payload` | 46 |  |  | 2 |  |
| `_append_effect` | 42 |  |  | 12 |  |
| `_require_project_available` | 40 |  |  | 1 |  |
| `_append_checkpoint` | 38 |  |  | 2 |  |
| `_d2_binding_for_item` | 37 |  |  | 3 |  |
| `_resolution_observation` | 30 |  |  | 6 |  |
| `_reject_runtime_adjustments` | 27 |  |  | 1 |  |
| `durability_profile_binding` | 21 | 是 | 0 | 2 |  |
| `_ensure_attempt_cleanup_coordinator` | 21 |  |  | 2 |  |
| `_require_attempt_binding` | 18 |  |  | 4 |  |
| `_selection_binding` | 17 |  |  | 5 |  |
| `_abort_initialization` | 16 |  |  | 0 |  |
| `_require_record_binding` | 16 |  |  | 1 |  |
| `settle_adjustment` | 15 | 是 | 1 | 2 | server/live_voice/persistent_task_core.py |
| `_require_item` | 13 |  |  | 7 |  |
| `_adjustment_delivery` | 10 |  |  | 5 |  |
| `construction_capability_profiles` | 9 | 是 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `stream_observer_failure_count` | 8 | 是 | 0 | 0 |  |
| `_consume_attempt_cleanup_result` | 7 |  |  | 1 |  |
| `capability_profiles` | 6 | 是 | 1 | 2 | server/live_voice/p3_authenticated_composition.py |
| `_record_stream_observer_failure` | 6 |  |  | 2 |  |
| `_settle_worker` | 6 |  |  | 1 |  |
| `_admitted_adjustments_pending` | 5 |  |  | 2 |  |
| `capability_profile` | 4 | 是 | 0 | 1 |  |
| `has_live_workers` | 4 | 是 | 0 | 0 |  |
| `retained_cleanup_attempt_ids` | 4 | 是 | 0 | 0 |  |
| `dispatch` | 3 | 是 | 3 | 35 | gateway/routing/session_sharing.py, server/live_voice/persistent_task_core.py, server/live_voice/product_composition_registry.py |
| `database` | 2 | 是 | 0 | 14 |  |

## `AgentConversationRuntime`（`server/live_voice/agent_conversation_runtime.py`，4,442 行，89 个方法，其中公开 38 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `present_authoritative_text` | 274 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `task_presentation_runtime_authority` | 188 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `submit_committed_turn` | 176 | 是 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `__init__` | 175 |  |  | 3 |  |
| `_run_native_delegate` | 165 |  |  | 2 |  |
| `execute_native_delegate` | 154 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_register_committed_turn_submission` | 142 |  |  | 2 |  |
| `select_formal_context` | 134 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_complete_admission` | 113 |  |  | 2 |  |
| `persist_native_assistant_history` | 103 | 是 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `accept_task_origin` | 102 | 是 | 0 | 0 |  |
| `persist_native_user_history` | 102 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `accept_task_progress_notification` | 99 | 是 | 0 | 0 |  |
| `fail_task_presentation` | 93 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_shutdown_coordinator` | 92 |  |  | 3 |  |
| `_consume_agent_event` | 86 |  |  | 1 |  |
| `claim_conversation_effects` | 80 | 是 | 0 | 0 |  |
| `_register_legacy_dispatch` | 76 |  |  | 1 |  |
| `_apply_generation_interruption` | 75 |  |  | 1 |  |
| `begin_speculative_dialogue` | 73 | 是 | 0 | 0 |  |
| `close` | 72 | 是 | 0 | 22 |  |
| `dispatch_committed_turn` | 66 | 是 | 0 | 0 |  |
| `execute_native_work` | 62 | 是 | 1 | 0 | server/live_voice/native_business_router.py |
| `attach_notification_consumer` | 60 | 是 | 0 | 0 |  |
| `_consume_progress` | 60 |  |  | 1 |  |
| `snapshot` | 58 | 是 | 0 | 59 |  |
| `schedule_native_assistant_history` | 56 | 是 | 0 | 0 |  |
| `start` | 54 | 是 | 0 | 5 |  |
| `acknowledge_presentation` | 53 | 是 | 3 | 0 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/native_interaction_runtime.py, server/live_voice/product_composition_registry.py |
| `_complete_committed_turn_submission` | 51 |  |  | 1 |  |
| `commit_turn` | 49 | 是 | 1 | 4 | server/live_voice/conversation_runtime_loop.py |
| `_apply_presentation_ack` | 49 |  |  | 1 |  |
| `acknowledge_conversation_effects` | 48 | 是 | 0 | 0 |  |
| `close_interaction` | 48 | 是 | 0 | 0 |  |
| `presented_agent_analysis` | 47 | 是 | 2 | 0 | server/live_voice/product_composition_registry.py, server/live_voice/product_p2_interaction_adapter.py |
| `interrupt_generation` | 46 | 是 | 1 | 2 | server/live_voice/product_composition_registry.py |
| `drain_notifications_for` | 45 | 是 | 0 | 0 |  |
| `task_notification_foreground_safe` | 40 | 是 | 2 | 1 | server/live_voice/native_business_router.py, server/live_voice/product_composition_registry.py |
| `_prune_invalid_output_effects` | 40 |  |  | 4 |  |
| `_validate_effect_ack_ids` | 38 |  |  | 1 |  |
| `_validate_notification_consumer` | 38 |  |  | 1 |  |
| `_complete_effect_claim` | 37 |  |  | 1 |  |
| `_admission_fingerprint` | 37 |  |  | 2 |  |
| `next_notification_for` | 36 | 是 | 0 | 0 |  |
| `_close_task_presentation_reservation` | 29 |  |  | 2 |  |
| `_generation_round_cancel_command` | 28 |  |  | 1 |  |
| `_formal_context_ref` | 27 |  |  | 2 |  |
| `_retry_history` | 27 |  |  | 1 |  |
| `start_turn` | 26 | 是 | 2 | 7 | server/live_voice/conversation_runtime_loop.py, server/live_voice/native_interaction_runtime.py |
| `next_notification` | 26 | 是 | 2 | 0 | server/live_voice/product_composition_registry.py, server/live_voice/product_p2_interaction_adapter.py |
| `_validate_effect_claim_id` | 26 |  |  | 2 |  |
| `_require_exact_commit` | 25 |  |  | 2 |  |
| `_require_notification_lease` | 25 |  |  | 4 |  |
| `_commit_admitted_turn` | 24 |  |  | 1 |  |
| `create_native_interaction_runtime_owner` | 23 | 是 | 0 | 0 |  |
| `_claim_product_identity` | 20 |  |  | 3 |  |
| `_require_started` | 19 |  |  | 12 |  |
| `_require_effect_lease` | 19 |  |  | 5 |  |
| `_complete_presentation_ack` | 18 |  |  | 1 |  |
| `_await_presentation_ack` | 18 |  |  | 2 |  |
| `_reserve_final_notification_drain` | 18 |  |  | 2 |  |
| `_run_native_history_writer` | 16 |  |  | 1 |  |
| `_validate_dispatch_channel` | 15 |  |  | 4 |  |
| `_retain_effects` | 14 |  |  | 2 |  |
| `_require_interruption_id` | 13 |  |  | 1 |  |
| `_consume_bridge` | 13 |  |  | 1 |  |
| `_detach_notification_record` | 13 |  |  | 3 |  |
| `_close_interaction_after_terminal` | 12 |  |  | 2 |  |
| `_supersede_effect_claims` | 12 |  |  | 1 |  |
| `detach_notification_consumer` | 11 | 是 | 0 | 0 |  |
| `_task_history_metadata` | 10 |  |  | 1 |  |
| `barge_in` | 9 | 是 | 2 | 2 | server/live_voice/native_interaction_runtime.py, server/live_voice/product_composition_registry.py |
| `_response_record` | 9 |  |  | 0 |  |
| `_requeue_effects_in_order` | 9 |  |  | 2 |  |
| `_facade_available` | 9 |  |  | 3 |  |
| `_release_product_identity` | 8 |  |  | 3 |  |
| `retry_user_history` | 8 | 是 | 0 | 0 |  |
| `_retain_generation_interruption` | 8 |  |  | 1 |  |
| `_require_admission` | 8 |  |  | 12 |  |
| `_validate_turn_commit` | 7 |  |  | 4 |  |
| `_require_exact_ack` | 7 |  |  | 2 |  |
| `_publish` | 7 |  |  | 5 |  |
| `retry_history` | 6 | 是 | 0 | 0 |  |
| `_interruption_timestamp` | 6 |  |  | 1 |  |
| `request_response_cancel` | 5 | 是 | 1 | 1 | server/live_voice/conversation_runtime_loop.py |
| `speculation_snapshot` | 5 | 是 | 0 | 0 |  |
| `_persist_user_history` | 5 |  |  | 4 |  |
| `_unwrap_admission` | 5 |  |  | 3 |  |
| `open_interaction` | 3 | 是 | 3 | 1 | server/live_voice/conversation_runtime_loop.py, server/live_voice/native_interaction_runtime.py, server/live_voice/product_p2_interaction_adapter.py |

## `P3AuthenticatedComposition`（`server/live_voice/p3_authenticated_composition.py`，3,982 行，67 个方法，其中公开 38 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `handle_production_resolution` | 714 | 是 | 1 | 2 | server/live_voice/product_composition_registry.py |
| `handle` | 340 | 是 | 7 | 2 | agents/harness/common/auto_harness/capabilities.py, agents/harness/common/auto_harness/service.py, agents/harness/common/tools/browser-move/src/openjiuwen_patch_sources/openjiuwen/core/workflow/components/llm/questioner_comp.py |
| `_validate_params` | 297 |  |  | 3 |  |
| `prepare_mutation_confirmation` | 162 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `validated_live_voice_configuration` | 146 | 是 | 0 | 0 |  |
| `resolve_product_authority_candidate` | 138 | 是 | 0 | 0 |  |
| `prepare_production_intent_authority` | 104 | 是 | 0 | 1 |  |
| `__init__` | 92 |  |  | 4 |  |
| `resolve_production_semantics` | 91 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_resolve_retry_snapshot` | 80 |  |  | 2 |  |
| `read_task_control_snapshot` | 76 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `query` | 73 | 是 | 2 | 21 | agents/harness/common/tools/wiki_tools.py, server/live_voice/native_business_router.py |
| `reauthorize_mutation_replay` | 69 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_read_product_unread_events` | 68 |  |  | 1 |  |
| `_require_product_presentation_authority` | 63 |  |  | 4 |  |
| `prepare_product_presentation_ack` | 59 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_read_status_retry_admission` | 57 |  |  | 2 |  |
| `_task_unread_page_from_result` | 55 |  |  | 1 |  |
| `stop` | 54 | 是 | 16 | 0 | agents/harness/common/auto_harness/service.py, agents/harness/common/memory/dreaming/__init__.py, agents/harness/common/memory/manager.py |
| `execute_product_presentation_ack` | 52 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_verify_confirmation` | 49 |  |  | 1 |  |
| `_require_task_context` | 48 |  |  | 2 |  |
| `read_product_status_diagnostics` | 47 | 是 | 0 | 0 |  |
| `create_product_progress_source` | 45 | 是 | 0 | 0 |  |
| `prepare_native_activation_authority` | 44 | 是 | 0 | 0 |  |
| `read_current_background_task` | 42 | 是 | 0 | 0 |  |
| `read_background_task` | 40 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_require_list_result_contexts` | 39 |  |  | 3 |  |
| `_resolve_native_activation_authority` | 38 |  |  | 3 |  |
| `read_current_background_task_native` | 38 | 是 | 0 | 0 |  |
| `read_task_notification_facts` | 38 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `read_product_status_retry_admission` | 37 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `create_product_subscription` | 35 | 是 | 0 | 0 |  |
| `_require_retry_task_identity` | 33 |  |  | 2 |  |
| `_require_consumer_task_context` | 33 |  |  | 2 |  |
| `_resolved_create_spec` | 30 |  |  | 1 |  |
| `_resolve_production_input_authority` | 28 |  |  | 6 |  |
| `require_local_artifact_delegation_capability` | 27 | 是 | 2 | 0 | server/live_voice/native_business_router.py, server/live_voice/product_composition_registry.py |
| `start` | 26 | 是 | 0 | 0 |  |
| `_retry_product_request` | 26 |  |  | 1 |  |
| `read_task_creation_origins` | 26 | 是 | 0 | 0 |  |
| `_select_create_executor` | 24 |  |  | 2 |  |
| `read_product_unread_events` | 24 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_read_product_task_result` | 22 |  |  | 1 |  |
| `handle_native` | 22 | 是 | 0 | 0 |  |
| `next_product_p2_response_generation` | 21 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_require_list_task_contexts` | 20 |  |  | 3 |  |
| `read_product_task_result` | 20 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `count_scope_tasks` | 18 | 是 | 0 | 0 |  |
| `_reconcile_loop` | 17 |  |  | 1 |  |
| `_select_production_create_candidate` | 17 |  |  | 3 |  |
| `_require_exact_task_context` | 15 |  |  | 13 |  |
| `_retry_facts` | 15 |  |  | 2 |  |
| `_require_retry_executor` | 15 |  |  | 3 |  |
| `_run_blocking` | 14 |  |  | 43 |  |
| `require_local_task_control_capability` | 13 | 是 | 2 | 0 | server/live_voice/native_business_router.py, server/live_voice/product_composition_registry.py |
| `_production_origin_payload` | 10 |  |  | 1 |  |
| `_enter_operation` | 9 |  |  | 14 |  |
| `product_progress_authority_atomic_replay` | 7 | 是 | 0 | 0 |  |
| `product_presentation_consumption_available` | 7 | 是 | 0 | 0 |  |
| `_production_capability_digest` | 7 |  |  | 1 |  |
| `task_database_path` | 5 | 是 | 0 | 0 |  |
| `_leave_operation` | 5 |  |  | 14 |  |
| `production_intent_available` | 4 | 是 | 0 | 1 |  |
| `reconcile_once` | 3 | 是 | 0 | 4 |  |
| `accepting` | 2 | 是 | 0 | 2 |  |
| `mutation_authority_ready` | 2 | 是 | 0 | 0 |  |

## `PersistentTaskCore`（`server/live_voice/persistent_task_core.py`，1,354 行，23 个方法，其中公开 13 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `execute` | 348 | 是 | 12 | 4 | agents/harness/common/memory/manager.py, agents/harness/common/tools/browser-move/src/openjiuwen_patch_sources/openjiuwen/core/session/checkpointer/persistence.py, agents/harness/common/tools/browser-move/src/openjiuwen_patch_sources/openjiuwen/core/single_agent/agents/react_agent.py |
| `reconcile_status` | 180 | 是 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `query` | 165 | 是 | 3 | 40 | agents/harness/common/tools/wiki_tools.py, server/live_voice/native_business_router.py, server/live_voice/p3_authenticated_composition.py |
| `recover_durable_attempt` | 118 | 是 | 0 | 1 |  |
| `_deliver_outbox` | 112 |  |  | 2 |  |
| `drain_inflight_adjustments` | 41 | 是 | 1 | 0 | server/live_voice/p3_authenticated_composition.py |
| `reconcile` | 39 | 是 | 3 | 0 | agents/harness/common/auto_harness/issue_fix/issue_runner.py, gateway/live_voice/dedicated_media_registration.py, server/live_voice/p3_authenticated_composition.py |
| `drain_outbox_once` | 38 | 是 | 0 | 2 |  |
| `_await_adjustment_delivery` | 30 |  |  | 1 |  |
| `_validate_retry_context` | 28 |  |  | 1 |  |
| `_require_retry_readiness` | 28 |  |  | 2 |  |
| `read_current_retry_admission` | 27 | 是 | 0 | 0 |  |
| `_reap_adjustment_deliveries` | 26 |  |  | 3 |  |
| `_publish_reconciliation_events` | 18 |  |  | 2 |  |
| `__init__` | 17 |  |  | 0 |  |
| `_own_adjustment_settlement` | 17 |  |  | 4 |  |
| `read_applied_retry_replay` | 16 | 是 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `_fence_adjustment_delivery` | 11 |  |  | 2 |  |
| `read_consumer_task` | 9 | 是 | 1 | 0 | server/live_voice/p3_authenticated_composition.py |
| `read_consumer_task_result` | 9 | 是 | 1 | 0 | server/live_voice/p3_authenticated_composition.py |
| `read_current_retry_authority` | 9 | 是 | 1 | 2 | server/live_voice/p3_authenticated_composition.py |
| `_task_read_projection` | 9 |  |  | 2 |  |
| `drain_outbox` | 6 | 是 | 0 | 0 |  |

## `ConversationRuntimeLoop`（`server/live_voice/conversation_runtime_loop.py`，1,392 行，75 个方法，其中公开 35 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_acknowledge_presentation_with_history` | 84 |  |  | 1 |  |
| `__init__` | 60 |  |  | 2 |  |
| `_apply_new_generation_interrupt` | 58 |  |  | 1 |  |
| `accept_response` | 50 | 是 | 2 | 1 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py |
| `post_barge_in` | 48 | 是 | 0 | 1 |  |
| `_apply_new_barge_in` | 48 |  |  | 1 |  |
| `_post` | 40 |  |  | 10 |  |
| `_require_acknowledgeable_output` | 38 |  |  | 3 |  |
| `transition_response` | 37 | 是 | 2 | 1 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py |
| `post_response_cancel` | 37 | 是 | 0 | 1 |  |
| `commit_turn` | 34 | 是 | 1 | 1 | server/live_voice/agent_conversation_runtime.py |
| `post_generation_interrupt` | 34 | 是 | 0 | 1 |  |
| `_request_response_cancel` | 34 |  |  | 2 |  |
| `_barge_in` | 33 |  |  | 1 |  |
| `_run` | 32 |  |  | 1 |  |
| `_settle_generation_interrupt` | 26 |  |  | 1 |  |
| `_evict_retained_generation_interrupts` | 25 |  |  | 1 |  |
| `close` | 24 | 是 | 0 | 0 |  |
| `transition_interaction` | 24 | 是 | 2 | 1 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py |
| `_emit_effect` | 24 |  |  | 5 |  |
| `claim_effects` | 23 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `start` | 21 | 是 | 0 | 0 |  |
| `post_presentation_ack_with_history` | 20 | 是 | 0 | 1 |  |
| `_enqueue_unit` | 20 |  |  | 1 |  |
| `_invalidate_pending_output` | 20 |  |  | 3 |  |
| `_require_admission` | 19 |  |  | 5 |  |
| `commit_native_turn` | 18 | 是 | 1 | 1 | server/live_voice/native_interaction_runtime.py |
| `cancel_response_if_running` | 18 | 是 | 1 | 0 | server/live_voice/native_interaction_runtime.py |
| `_next_operation` | 17 |  |  | 1 |  |
| `seal_presentation` | 16 | 是 | 1 | 0 | server/live_voice/native_interaction_runtime.py |
| `invalidate_presentation` | 16 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `_generation_interrupt` | 16 |  |  | 1 |  |
| `_require_current_output` | 15 |  |  | 5 |  |
| `snapshot` | 14 | 是 | 0 | 17 |  |
| `_require_same_generation_interrupt_target` | 13 |  |  | 1 |  |
| `_acknowledge_presentation` | 12 |  |  | 1 |  |
| `_emit_playback_stop_once` | 12 |  |  | 5 |  |
| `_mark_effect_presented` | 12 |  |  | 2 |  |
| `_shutdown_state` | 12 |  |  | 1 |  |
| `presentation_complete` | 10 | 是 | 1 | 1 | server/live_voice/native_interaction_runtime.py |
| `barge_in` | 10 | 是 | 3 | 2 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py, server/live_voice/product_composition_registry.py |
| `_produce_unit` | 9 |  |  | 1 |  |
| `_response_record` | 9 |  |  | 7 |  |
| `_apply_operation` | 9 |  |  | 1 |  |
| `acknowledge_presentation_with_history` | 8 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `_history_policy` | 8 |  |  | 1 |  |
| `_require_id` | 8 |  |  | 8 |  |
| `_require_owner_loop` | 7 |  |  | 3 |  |
| `_validate_capacity` | 7 |  |  | 2 |  |
| `acknowledge_response_cancel` | 6 | 是 | 0 | 1 |  |
| `mark_response_cancel_unknown` | 6 | 是 | 0 | 1 |  |
| `post_enqueue_unit` | 6 | 是 | 0 | 1 |  |
| `post_presentation_ack` | 6 | 是 | 0 | 1 |  |
| `interrupt_generation` | 6 | 是 | 2 | 0 | server/live_voice/agent_conversation_runtime.py, server/live_voice/product_composition_registry.py |
| `response_fence_state` | 6 | 是 | 1 | 1 | server/live_voice/agent_conversation_runtime.py |
| `_clear_pending_barge` | 6 |  |  | 1 |  |
| `_clear_pending_cancel` | 6 |  |  | 1 |  |
| `_response_records` | 6 |  |  | 2 |  |
| `_resolved_future` | 6 |  |  | 3 |  |
| `_failed_future` | 6 |  |  | 4 |  |
| `_fail_pending` | 6 |  |  | 1 |  |
| `_latest_response_record` | 5 |  |  | 3 |  |
| `open_interaction` | 4 | 是 | 3 | 1 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py, server/live_voice/product_p2_interaction_adapter.py |
| `start_turn` | 4 | 是 | 2 | 1 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py |
| `request_response_cancel` | 4 | 是 | 1 | 3 | server/live_voice/agent_conversation_runtime.py |
| `enqueue_unit` | 4 | 是 | 2 | 0 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py |
| `presented_history` | 4 | 是 | 0 | 1 |  |
| `_submit` | 4 |  |  | 14 |  |
| `_fence_presentation` | 3 |  |  | 7 |  |
| `enabled` | 2 | 是 | 0 | 6 |  |
| `cancel_turn` | 2 | 是 | 0 | 1 |  |
| `post_produce_unit` | 2 | 是 | 0 | 1 |  |
| `produce_unit` | 2 | 是 | 2 | 0 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py |
| `acknowledge_presentation` | 2 | 是 | 3 | 0 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/native_interaction_runtime.py, server/live_voice/product_composition_registry.py |
| `_await_future` | 2 |  |  | 10 |  |

## `ProgressNotificationArbiter`（`server/live_voice/progress_notification_arbiter.py`，1,772 行，35 个方法，其中公开 4 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_validate_no_projection_advance` | 202 |  |  | 1 |  |
| `_offer_locked` | 199 |  |  | 2 |  |
| `_advance_without_projection_locked` | 197 |  |  | 1 |  |
| `_validate_offer` | 158 |  |  | 1 |  |
| `_resume_consumer_cursor` | 138 |  |  | 0 |  |
| `_begin_attempt_epoch` | 83 |  |  | 0 |  |
| `_validate_source_relation` | 66 |  |  | 1 |  |
| `__init__` | 56 |  |  | 8 |  |
| `_observe_identity` | 55 |  |  | 1 |  |
| `_drain_locked` | 50 |  |  | 1 |  |
| `_offer_consumer` | 45 |  |  | 0 |  |
| `_release_consumer_cursor` | 38 |  |  | 0 |  |
| `_delivery_decision` | 38 |  |  | 2 |  |
| `_acknowledge_locked` | 36 |  |  | 1 |  |
| `_capacity_reason` | 34 |  |  | 1 |  |
| `offer` | 29 | 是 | 2 | 1 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/task_progress_return.py |
| `_no_projection_capacity_reason` | 29 |  |  | 1 |  |
| `_validate_authenticated_scope` | 28 |  |  | 2 |  |
| `_decision` | 25 |  |  | 3 |  |
| `_consumer_cursor_stream_capacity_reason` | 23 |  |  | 2 |  |
| `_sequence_reason` | 21 |  |  | 1 |  |
| `_backpressure` | 21 |  |  | 2 |  |
| `_snapshot_locked` | 20 |  |  | 1 |  |
| `_advance_without_projection` | 19 |  |  | 0 |  |
| `_validate_foreground` | 19 |  |  | 2 |  |
| `_no_projection_sequence_reason` | 19 |  |  | 1 |  |
| `drain` | 14 | 是 | 8 | 2 | acp/stdio_client.py, agents/harness/common/rails/stream_event_rail.py, extensions/agentos/agentos_router/ssh_relay.py |
| `_attempt_epoch_reason` | 11 |  |  | 2 |  |
| `_foreground_safe` | 9 |  |  | 3 |  |
| `_lifecycle_reason` | 8 |  |  | 1 |  |
| `_may_replace` | 8 |  |  | 1 |  |
| `acknowledge` | 7 | 是 | 3 | 1 | gateway/live_voice/dedicated_media_route.py, server/live_voice/conversation_runtime_loop.py, server/live_voice/task_progress_return.py |
| `_rejected` | 7 |  |  | 12 |  |
| `snapshot` | 5 | 是 | 0 | 0 |  |
| `_accept_sequence` | 5 |  |  | 6 |  |

## `TaskProgressReturnBridge`（`server/live_voice/task_progress_return.py`，1,117 行，29 个方法，其中公开 4 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_consume` | 169 |  |  | 1 |  |
| `activate` | 154 | 是 | 4 | 0 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/product_composition_registry.py, server/live_voice/product_composition_root.py |
| `_deliver_voice` | 113 |  |  | 1 |  |
| `drain_voice` | 95 | 是 | 1 | 2 | server/live_voice/product_composition_registry.py |
| `__init__` | 93 |  |  | 5 |  |
| `_run` | 58 |  |  | 1 |  |
| `close` | 49 | 是 | 0 | 10 |  |
| `_emit_voice_intent` | 46 |  |  | 2 |  |
| `_advance_voice_without_projection` | 45 |  |  | 1 |  |
| `_prepared_source_usable` | 30 |  |  | 1 |  |
| `_deliver_text` | 29 |  |  | 1 |  |
| `snapshot` | 28 | 是 | 0 | 13 |  |
| `_notification_binding` | 19 |  |  | 2 |  |
| `_authorize` | 17 |  |  | 17 |  |
| `_inactive_activation` | 15 |  |  | 17 |  |
| `_log_voice_owner` | 14 |  |  | 3 |  |
| `_uses_exact_authority_source` | 12 |  |  | 7 |  |
| `_handoff_kind` | 12 |  |  | 4 |  |
| `_handoff_evidence` | 12 |  |  | 4 |  |
| `_close_impl` | 11 |  |  | 1 |  |
| `_consumer_terminal_closes_stream` | 11 |  |  | 2 |  |
| `_close_source` | 10 |  |  | 15 |  |
| `_settle` | 9 |  |  | 9 |  |
| `_uses_consumer_authority_source` | 8 |  |  | 10 |  |
| `_next_source_event` | 7 |  |  | 1 |  |
| `_subscription_matches` | 6 |  |  | 1 |  |
| `_start_source` | 5 |  |  | 1 |  |
| `_generation_current` | 5 |  |  | 11 |  |
| `_reject` | 3 |  |  | 49 |  |

## `SqliteUnifiedCommittedInputJournal`（`server/live_voice/unified_committed_input.py`，1,622 行，31 个方法，其中公开 19 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `__init__` | 152 |  |  | 0 |  |
| `admit` | 134 | 是 | 0 | 1 |  |
| `retain_semantic_context` | 125 | 是 | 0 | 0 |  |
| `admit_foreground_effect` | 120 | 是 | 0 | 0 |  |
| `complete_foreground_effect` | 118 | 是 | 0 | 0 |  |
| `checkpoint_foreground_effect` | 103 | 是 | 0 | 0 |  |
| `checkpoint_foreground_effect_result` | 98 | 是 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `complete` | 73 | 是 | 5 | 1 | server/live_voice/batch_speech.py, symphony/retrieval/llm/base/protocols.py, symphony/retrieval/llm/transformers_logit_selection/client.py |
| `consume_semantic_context` | 69 | 是 | 0 | 0 |  |
| `bind_semantic` | 68 | 是 | 0 | 0 |  |
| `read_foreground_effect` | 59 | 是 | 0 | 0 |  |
| `claim_foreground_effect_recovery` | 57 | 是 | 0 | 0 |  |
| `wait_for_completion` | 51 | 是 | 0 | 0 |  |
| `read_creation_origin` | 43 | 是 | 0 | 0 |  |
| `read_semantic_reference` | 32 | 是 | 0 | 0 |  |
| `_pending_context` | 31 |  |  | 8 |  |
| `renew` | 29 | 是 | 0 | 1 |  |
| `_validate_identity` | 25 |  |  | 2 |  |
| `read_semantic_contexts` | 21 | 是 | 0 | 0 |  |
| `_semantic_record_digest` | 19 |  |  | 3 |  |
| `_validate_voice_binding` | 19 |  |  | 6 |  |
| `_decode_recovery` | 19 |  |  | 6 |  |
| `_decode_semantic_binding` | 19 |  |  | 5 |  |
| `find_semantic_context` | 18 | 是 | 0 | 0 |  |
| `_decode_result` | 17 |  |  | 10 |  |
| `_semantic_text` | 13 |  |  | 4 |  |
| `_semantic_scope_key` | 12 |  |  | 7 |  |
| `read_semantic_analysis_history` | 12 | 是 | 0 | 0 |  |
| `_semantic_time` | 8 |  |  | 6 |  |
| `_connect` | 6 |  |  | 19 |  |
| `renewal_interval_seconds` | 4 | 是 | 0 | 0 |  |

## `StreamingSpeechConformance`（`server/live_voice/streaming_speech.py`，1,108 行，41 个方法，其中公开 17 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `accept_recognition_event` | 120 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `accept_recognition_boundary` | 114 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `accept_synthesis_event` | 105 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `_accept_synthesis_chunk` | 65 |  |  | 1 |  |
| `accept_audio_frame` | 60 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `start_recognition` | 50 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `start_synthesis` | 47 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `reap_terminal` | 43 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `__init__` | 41 |  |  | 4 |  |
| `_accept_synthesis_completed` | 30 |  |  | 1 |  |
| `activate_response` | 29 | 是 | 2 | 1 | gateway/live_voice/streaming_synthesis_route.py, server/live_voice/batch_speech.py |
| `_require_recognition` | 28 |  |  | 5 |  |
| `_require_synthesis` | 27 |  |  | 3 |  |
| `expire` | 23 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `_snapshot_unlocked` | 22 |  |  | 2 |  |
| `close` | 21 | 是 | 0 | 4 |  |
| `_accept_synthesis_cancelled` | 20 |  |  | 1 |  |
| `request_recognition_cancel` | 15 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `request_synthesis_cancel` | 15 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `_accept_synthesis_started` | 15 |  |  | 1 |  |
| `_require_operational` | 14 |  |  | 1 |  |
| `_require_start_allowed` | 12 |  |  | 3 |  |
| `_now` | 12 |  |  | 4 |  |
| `_make_response_capacity` | 11 |  |  | 1 |  |
| `_advance_synthesis_audio` | 10 |  |  | 2 |  |
| `_retain_control` | 10 |  |  | 2 |  |
| `_require_live_recognition` | 9 |  |  | 1 |  |
| `_request_recognition_cancel` | 9 |  |  | 5 |  |
| `_require_before_deadline_recognition` | 8 |  |  | 3 |  |
| `_require_before_deadline_synthesis` | 8 |  |  | 1 |  |
| `_deadline` | 8 |  |  | 3 |  |
| `_fail_recognition` | 7 |  |  | 4 |  |
| `_fail_synthesis` | 7 |  |  | 17 |  |
| `_request_synthesis_cancel` | 7 |  |  | 5 |  |
| `_require_not_terminal_recognition` | 6 |  |  | 4 |  |
| `_require_not_terminal_synthesis` | 6 |  |  | 2 |  |
| `provider_closed_recognition` | 5 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `provider_closed_synthesis` | 5 | 是 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `take_provider_controls` | 5 | 是 | 0 | 0 |  |
| `snapshot` | 3 | 是 | 0 | 0 |  |
| `capability` | 2 | 是 | 1 | 21 | server/live_voice/batch_speech.py |

## `OpenAIStreamingSpeechProvider`（`server/live_voice/openai_streaming_speech.py`，1,489 行，49 个方法，其中公开 16 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_consume_recognition_message` | 181 |  |  | 1 |  |
| `open_recognition` | 119 | 是 | 1 | 1 | gateway/live_voice/streaming_speech_route.py |
| `_close_serialized` | 106 |  |  | 1 |  |
| `_receive_recognition` | 71 |  |  | 1 |  |
| `__init__` | 68 |  |  | 6 |  |
| `send_recognition_audio` | 64 | 是 | 1 | 0 | gateway/live_voice/streaming_speech_route.py |
| `commit_recognition` | 62 | 是 | 1 | 1 | gateway/live_voice/streaming_speech_route.py |
| `_run_synthesis` | 62 |  |  | 1 |  |
| `_consume_sse_event` | 47 |  |  | 2 |  |
| `open_synthesis` | 43 | 是 | 1 | 1 | gateway/live_voice/streaming_synthesis_route.py |
| `_send_recognition_wire` | 43 |  |  | 4 |  |
| `_open_synthesis_stream` | 38 |  |  | 1 |  |
| `_read_synthesis_sse_event` | 38 |  |  | 1 |  |
| `_publish_synthesis` | 35 |  |  | 4 |  |
| `_publish_recognition` | 32 |  |  | 2 |  |
| `_fail_recognition_transport` | 29 |  |  | 2 |  |
| `_put_bounded` | 27 |  |  | 3 |  |
| `next_recognition_event` | 26 | 是 | 1 | 0 | gateway/live_voice/streaming_speech_route.py |
| `_rollback_failed_recognition` | 26 |  |  | 1 |  |
| `_rollback_failed_synthesis` | 24 |  |  | 1 |  |
| `_finalize_cleanup_owners` | 24 |  |  | 1 |  |
| `_publish_recognition_boundary` | 23 |  |  | 3 |  |
| `_emit_failure` | 23 |  |  | 4 |  |
| `_open_recognition_socket` | 22 |  |  | 1 |  |
| `_diagnose_recognition` | 19 |  |  | 9 |  |
| `cancel_synthesis` | 15 | 是 | 1 | 1 | gateway/live_voice/streaming_synthesis_route.py |
| `cleanup_snapshot` | 14 | 是 | 0 | 4 |  |
| `cancel_recognition` | 14 | 是 | 1 | 1 | gateway/live_voice/streaming_speech_route.py |
| `_consume_synthesis_stream` | 14 |  |  | 1 |  |
| `_require_cleanup_capacity` | 14 |  |  | 2 |  |
| `_recognition_event_cursor` | 11 |  |  | 1 |  |
| `_bind_item` | 9 |  |  | 4 |  |
| `next_synthesis_event` | 8 | 是 | 1 | 0 | gateway/live_voice/streaming_synthesis_route.py |
| `_committed_cursor` | 8 |  |  | 1 |  |
| `_require_recognition` | 8 |  |  | 4 |  |
| `_require_synthesis` | 7 |  |  | 2 |  |
| `_require_committed` | 6 |  |  | 4 |  |
| `_retire_recognition` | 6 |  |  | 5 |  |
| `_retire_synthesis` | 6 |  |  | 4 |  |
| `_require_open` | 5 |  |  | 2 |  |
| `_close_stream` | 4 |  |  | 7 |  |
| `close` | 3 | 是 | 0 | 18 |  |
| `capability` | 2 | 是 | 1 | 0 | server/live_voice/batch_speech.py |
| `conformance` | 2 | 是 | 0 | 1 |  |
| `synthesis_model` | 2 | 是 | 0 | 0 |  |
| `synthesis_voice` | 2 | 是 | 0 | 0 |  |
| `fallback_tier` | 2 | 是 | 0 | 3 |  |
| `degradation_facts` | 2 | 是 | 0 | 0 |  |
| `_close_socket` | 2 |  |  | 10 |  |

## `FormalBatchSpeechService`（`server/live_voice/batch_speech.py`，1,207 行，30 个方法，其中公开 7 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_recognize_once` | 104 |  |  | 1 |  |
| `_synthesize_once` | 94 |  |  | 1 |  |
| `cancel` | 93 | 是 | 68 | 11 | acp/stdio_client.py, agents/harness/common/auto_harness/scheduler.py, agents/harness/common/auto_harness/service.py |
| `_run_operation` | 90 |  |  | 1 |  |
| `issue_streaming_voice_commit_receipt` | 83 | 是 | 0 | 1 |  |
| `claim_voice_commit_receipt` | 79 | 是 | 0 | 0 |  |
| `recognize` | 71 | 是 | 1 | 5 | agents/harness/common/tools/browser-move/src/openjiuwen_patch_sources/openjiuwen/core/controller/modules/intent_recognizer.py |
| `synthesize` | 66 | 是 | 1 | 5 | gateway/live_voice/dedicated_media_registration.py |
| `capability_payload` | 61 | 是 | 2 | 0 | gateway/channel_manager/web/app_web_handlers.py, gateway/live_voice/speech_rpc.py |
| `_execute` | 60 |  |  | 2 |  |
| `__init__` | 50 |  |  | 4 |  |
| `_close_once` | 49 |  |  | 1 |  |
| `_reserve_capture` | 49 |  |  | 1 |  |
| `_record_worker_terminal` | 26 |  |  | 3 |  |
| `_authorize` | 25 |  |  | 2 |  |
| `_reserve_response` | 23 |  |  | 1 |  |
| `_fence_entry` | 21 |  |  | 6 |  |
| `_evict_completed_locked` | 19 |  |  | 1 |  |
| `close` | 18 | 是 | 0 | 2 |  |
| `_invoke_worker` | 16 |  |  | 1 |  |
| `_fence_error` | 13 |  |  | 4 |  |
| `_issue_voice_commit_receipt` | 12 |  |  | 1 |  |
| `_ensure_response_current` | 10 |  |  | 1 |  |
| `_ensure_capture_current` | 8 |  |  | 1 |  |
| `_require_authenticated` | 7 |  |  | 2 |  |
| `_bounded_identity_put` | 7 |  |  | 4 |  |
| `_mark_provider_completion_known` | 6 |  |  | 2 |  |
| `_consume_background_task` | 5 |  |  | 1 |  |
| `_prune_voice_commit_receipts_locked` | 4 |  |  | 2 |  |
| `_ensure_not_fenced` | 4 |  |  | 3 |  |

## `StreamingSynthesisRouteOwner`（`gateway/live_voice/streaming_synthesis_route.py`，1,634 行，37 个方法，其中公开 10 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_begin_prepared` | 320 |  |  | 1 |  |
| `_run_close_cleanup` | 115 |  |  | 1 |  |
| `_terminate_locked` | 110 |  |  | 1 |  |
| `_failure_outcome` | 109 |  |  | 14 |  |
| `_produce` | 102 |  |  | 1 |  |
| `_next_chunk_locked` | 99 |  |  | 1 |  |
| `_activate_response` | 73 |  |  | 1 |  |
| `_validate_event` | 68 |  |  | 1 |  |
| `__init__` | 52 |  |  | 3 |  |
| `_enqueue_frame` | 41 |  |  | 2 |  |
| `_watch_retirement` | 39 |  |  | 1 |  |
| `_select` | 37 |  |  | 2 |  |
| `cancel` | 36 | 是 | 68 | 11 | acp/stdio_client.py, agents/harness/common/auto_harness/scheduler.py, agents/harness/common/auto_harness/service.py |
| `_cancel_provider` | 35 |  |  | 10 |  |
| `_complete` | 29 |  |  | 1 |  |
| `close` | 28 | 是 | 0 | 6 |  |
| `available` | 24 | 是 | 1 | 8 | gateway/live_voice/dedicated_media_registration.py |
| `_forget_retired_handle` | 24 |  |  | 2 |  |
| `_close_provider_once` | 22 |  |  | 3 |  |
| `begin` | 21 | 是 | 5 | 2 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/product_streaming_synthesis.py, server/live_voice/conversation_runtime.py |
| `next_chunk` | 21 | 是 | 1 | 0 | gateway/live_voice/product_streaming_synthesis.py |
| `_preflight_response` | 20 |  |  | 1 |  |
| `_require_handle` | 20 |  |  | 3 |  |
| `_open_provider_guarded` | 19 |  |  | 1 |  |
| `wait_for_retained_cleanup` | 17 | 是 | 1 | 0 | gateway/live_voice/product_streaming_synthesis.py |
| `_terminate` | 17 |  |  | 13 |  |
| `_cleanup_interrupted_pull` | 15 |  |  | 2 |  |
| `_queue_put_guarded` | 15 |  |  | 2 |  |
| `_discard_unstarted` | 12 |  |  | 3 |  |
| `_invoke_selector` | 9 |  |  | 1 |  |
| `_selection_reason` | 9 |  |  | 1 |  |
| `selection_degradation` | 7 | 是 | 0 | 0 |  |
| `_take_process_control` | 7 |  |  | 2 |  |
| `_retire` | 3 |  |  | 4 |  |
| `active_count` | 2 | 是 | 0 | 0 |  |
| `retained_task_count` | 2 | 是 | 0 | 0 |  |
| `retained_task_capacity` | 2 | 是 | 0 | 0 |  |

## `StreamingRecognitionRouteOwner`（`gateway/live_voice/streaming_speech_route.py`，1,289 行，41 个方法，其中公开 10 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `close` | 171 | 是 | 0 | 10 |  |
| `finish` | 161 | 是 | 4 | 6 | agents/harness/common/rails/stream_event_rail.py, gateway/live_voice/dedicated_media_registration.py, server/live_voice/openai_streaming_speech.py |
| `begin` | 157 | 是 | 5 | 2 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/product_streaming_synthesis.py, server/live_voice/conversation_runtime.py |
| `_collect_final` | 77 |  |  | 1 |  |
| `_select` | 74 |  |  | 2 |  |
| `_accept_turn_boundary` | 58 |  |  | 1 |  |
| `__init__` | 44 |  |  | 0 |  |
| `_pump` | 39 |  |  | 1 |  |
| `abort` | 36 | 是 | 5 | 5 | agents/harness/common/rails/stream_event_rail.py, gateway/live_voice/dedicated_media_registration.py, server/runtime/agent_adapter/interface.py |
| `_bounded_provider_close` | 34 |  |  | 2 |  |
| `_retain_provider_close_obligation` | 33 |  |  | 2 |  |
| `offer` | 32 | 是 | 2 | 0 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/task_progress_return.py |
| `_run_selector` | 29 |  |  | 1 |  |
| `_start_provider_task` | 26 |  |  | 3 |  |
| `_cancel_local_task` | 23 |  |  | 3 |  |
| `_start_provider_cleanup_task` | 22 |  |  | 1 |  |
| `_diagnose` | 21 |  |  | 8 |  |
| `_await_bounded_provider_task` | 21 |  |  | 2 |  |
| `_fallback` | 15 |  |  | 11 |  |
| `_prune_provider_close_tasks` | 13 |  |  | 3 |  |
| `_release_opening_task` | 12 |  |  | 1 |  |
| `_bounded_provider_call` | 11 |  |  | 5 |  |
| `available` | 10 | 是 | 1 | 2 | gateway/live_voice/dedicated_media_registration.py |
| `end_of_turn_available` | 10 | 是 | 0 | 0 |  |
| `_release_provider_task` | 10 |  |  | 2 |  |
| `_complete_provider_close_obligation` | 9 |  |  | 2 |  |
| `_selection_reason` | 9 |  |  | 1 |  |
| `wait_end_of_turn` | 7 | 是 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `wait_speech_start` | 7 | 是 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `_stream_key` | 7 |  |  | 2 |  |
| `_safe_process_control` | 6 |  |  | 7 |  |
| `_release_stream_reservation` | 6 |  |  | 3 |  |
| `selection_degradation` | 5 | 是 | 0 | 0 |  |
| `_release_provider_cleanup_task_capacity` | 5 |  |  | 4 |  |
| `_retain_provider_task` | 5 |  |  | 8 |  |
| `_release_provider_task_capacity` | 5 |  |  | 3 |  |
| `_release_handle` | 5 |  |  | 1 |  |
| `_prune_provider_cleanup_task_capacity` | 4 |  |  | 1 |  |
| `_prune_provider_task_capacity` | 4 |  |  | 1 |  |
| `_prune_retained_provider_tasks` | 4 |  |  | 2 |  |
| `_take_retained_process_control` | 4 |  |  | 2 |  |

## `TaskEventSubscription`（`server/live_voice/task_event_subscription.py`，1,395 行，27 个方法，其中公开 4 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_accept_batch` | 409 |  |  | 2 |  |
| `_start_authority_atomic_replay` | 217 |  |  | 1 |  |
| `_start_authorized_baseline` | 115 |  |  | 1 |  |
| `__init__` | 113 |  |  | 0 |  |
| `_poll_loop` | 83 |  |  | 2 |  |
| `_validate_attempt_snapshot` | 73 |  |  | 3 |  |
| `next_event` | 53 | 是 | 2 | 1 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/task_progress_return.py |
| `start` | 48 | 是 | 0 | 8 |  |
| `close` | 42 | 是 | 0 | 6 |  |
| `_validate_start_snapshot` | 37 |  |  | 3 |  |
| `snapshot` | 29 | 是 | 0 | 24 |  |
| `_require_owner_loop` | 18 |  |  | 3 |  |
| `_request_detach` | 17 |  |  | 5 |  |
| `_authorize_current_read` | 16 |  |  | 10 |  |
| `_start_authority_tail_if_ready` | 14 |  |  | 1 |  |
| `_cleanup_preallocation_start_failure` | 13 |  |  | 1 |  |
| `_fail` | 13 |  |  | 10 |  |
| `_scope_matches` | 10 |  |  | 2 |  |
| `_settle_start_close_intent` | 9 |  |  | 15 |  |
| `_discard_queued_events` | 7 |  |  | 2 |  |
| `_apply_close_intent_on_owner` | 6 |  |  | 1 |  |
| `_remember_close_intent` | 5 |  |  | 2 |  |
| `_close_was_requested` | 3 |  |  | 3 |  |
| `_close_intent_reason` | 3 |  |  | 5 |  |
| `_signal_changed` | 3 |  |  | 6 |  |
| `__aiter__` | 2 |  |  | 0 |  |
| `__anext__` | 2 |  |  | 0 |  |

## `PresentationLedger`（`server/live_voice/presentation_ledger.py`，469 行，22 个方法，其中公开 10 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `acknowledge` | 61 | 是 | 3 | 0 | gateway/live_voice/dedicated_media_route.py, server/live_voice/conversation_runtime_loop.py, server/live_voice/task_progress_return.py |
| `presented_history` | 48 | 是 | 1 | 0 | server/live_voice/conversation_runtime_loop.py |
| `produce` | 41 | 是 | 1 | 1 | server/live_voice/conversation_runtime_loop.py |
| `seal_surface` | 29 | 是 | 1 | 0 | server/live_voice/conversation_runtime_loop.py |
| `close_surface` | 25 | 是 | 1 | 1 | server/live_voice/conversation_runtime_loop.py |
| `_validate_unit` | 25 |  |  | 1 |  |
| `_validate_cross_surface_alignment` | 24 |  |  | 1 |  |
| `snapshot` | 22 | 是 | 0 | 0 |  |
| `enqueue` | 21 | 是 | 3 | 0 | gateway/live_voice/dedicated_media_route.py, server/live_voice/conversation_runtime_loop.py, symphony/service.py |
| `begin_response` | 17 | 是 | 1 | 0 | server/live_voice/conversation_runtime_loop.py |
| `_validate_ack` | 17 |  |  | 1 |  |
| `__init__` | 15 |  |  | 5 |  |
| `_validate_utc` | 15 |  |  | 1 |  |
| `_unit_index` | 14 |  |  | 1 |  |
| `_key` | 11 |  |  | 4 |  |
| `invalidate_response` | 10 | 是 | 1 | 0 | server/live_voice/conversation_runtime_loop.py |
| `_refresh_completion` | 9 |  |  | 2 |  |
| `_require_response` | 9 |  |  | 5 |  |
| `_require_text` | 8 |  |  | 5 |  |
| `_require_uint` | 8 |  |  | 5 |  |
| `_require_open` | 7 |  |  | 4 |  |
| `presentation_complete` | 6 | 是 | 2 | 0 | server/live_voice/conversation_runtime_loop.py, server/live_voice/native_interaction_runtime.py |

## `JiuWenSwarmRoundHarness`（`server/live_voice/jiuwenswarm_round_harness.py`，811 行，24 个方法，其中公开 11 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_run_round` | 136 |  |  | 3 |  |
| `commit_round` | 114 | 是 | 1 | 1 | server/live_voice/agent_conversation_runtime.py |
| `reserve_round` | 85 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `cancel_round` | 77 | 是 | 2 | 2 | server/live_voice/agent_conversation_runtime.py, server/runtime/agent_adapter/interface_deep.py |
| `__init__` | 59 |  |  | 3 |  |
| `rollback_unstarted_round` | 44 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `_round_event` | 38 |  |  | 3 |  |
| `_require_reservation` | 23 |  |  | 4 |  |
| `abort_round_reservation` | 20 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `snapshot` | 20 | 是 | 0 | 0 |  |
| `_deliver_exact_cancel` | 20 |  |  | 1 |  |
| `_validate_chunk` | 19 |  |  | 1 |  |
| `_require_owner` | 18 |  |  | 7 |  |
| `begin_round_commit` | 17 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `_require_handle_record` | 15 |  |  | 5 |  |
| `_close_coordinator` | 14 |  |  | 1 |  |
| `_require_admission` | 14 |  |  | 1 |  |
| `_require_formal_facade` | 12 |  |  | 2 |  |
| `close` | 10 | 是 | 0 | 4 |  |
| `_expire` | 6 |  |  | 6 |  |
| `_timestamp` | 6 |  |  | 1 |  |
| `detach` | 3 | 是 | 2 | 4 | symphony/retrieval/llm/transformers_logit_selection/client.py, symphony/retrieval/llm/transformers_prefix_cached_generation/generation.py |
| `terminal_event` | 2 | 是 | 0 | 11 |  |
| `require_handle` | 2 | 是 | 0 | 2 |  |

## `AgentBridgeRuntime`（`server/live_voice/agent_bridge_runtime.py`，862 行，21 个方法，其中公开 10 个）

| 方法 | 行 | 公开 | callers | 文件内引用 | 调用方示例 |
|---|---:|---|---:|---:|---|
| `_run_request` | 269 |  |  | 1 |  |
| `__init__` | 73 |  |  | 3 |  |
| `commit_dispatch` | 68 | 是 | 1 | 2 | server/live_voice/agent_conversation_runtime.py |
| `reserve_dispatch` | 62 | 是 | 1 | 1 | server/live_voice/agent_conversation_runtime.py |
| `rollback_undelivered_dispatch` | 51 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `next_delivery` | 43 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `submit` | 34 | 是 | 11 | 0 | agents/harness/common/tools/browser-move/src/openjiuwen_patch_sources/openjiuwen/agent_evolving/optimizer/tool/utils/beam_search.py, gateway/live_voice/dedicated_media_registration.py, resources/agent/workspace/skills/skill-creator/scripts/run_eval.py |
| `_dispatch_loop` | 28 |  |  | 1 |  |
| `begin_dispatch_commit` | 27 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `abort_dispatch` | 26 | 是 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `start` | 23 | 是 | 0 | 0 |  |
| `_best_effort_close_adapter_stream` | 22 |  |  | 3 |  |
| `_require_admission` | 21 |  |  | 4 |  |
| `snapshot` | 19 | 是 | 0 | 0 |  |
| `_validate_agent_event` | 17 |  |  | 1 |  |
| `close` | 16 | 是 | 0 | 0 |  |
| `_validate_round_source` | 16 |  |  | 1 |  |
| `_require_owner_loop` | 7 |  |  | 5 |  |
| `_consume_cleanup_result` | 5 |  |  | 1 |  |
| `_request_finished` | 4 |  |  | 1 |  |
| `_put_output` | 4 |  |  | 2 |  |

