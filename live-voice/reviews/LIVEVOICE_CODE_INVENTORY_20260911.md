# Live Voice 逐文件代码量与模块归属（2026-09-11）

统计基线：JiuwenSwarm `537c5d2c9fc595fe38b2ccd1f93b8984fce594a3`。统计的是该基线已跟踪文件；本报告本身不计入基线。

物理行数含空行、注释与 docstring；非空行也不是严格 SLOC。用途是比较维护体量，不能当作复杂度、性能或质量指标。所有归属互斥。共享 SR/SS 文件只计一次。

主清单包括命名可识别专用代码和调用链补充的六个专用文件；其余共享入口在末尾单列，不把整个 App/server 文件冒充 Live Voice 净代码。静态进口图不等于运行覆盖；类型引用也会使模块显示可达。

| 模块 | 文件数 | 物理行 | 非空行 |
|---|---:|---:|---:|
| 音频设备与浏览器 I/O | 5 | 4,656 | 4,388 |
| Speech Recognition / Synthesis | 10 | 15,045 | 14,110 |
| Realtime Media | 13 | 21,254 | 20,119 |
| Conversation / Presentation | 9 | 11,970 | 11,197 |
| Native Provider / Interaction | 8 | 8,229 | 7,676 |
| Agent Bridge / Work | 12 | 10,976 | 10,275 |
| Task Core / Store | 5 | 20,583 | 19,912 |
| Executor / Durability | 9 | 10,834 | 10,143 |
| Task Semantics / Business Bridge | 21 | 11,841 | 11,017 |
| Product Composition / Authority | 8 | 27,101 | 25,905 |
| Observability / Diagnostics | 21 | 13,245 | 12,193 |
| Protocol / Shared Contract | 4 | 7,311 | 6,776 |
| Web Product / Task UI | 28 | 22,783 | 21,766 |
| Configuration / Deployment | 5 | 2,528 | 2,290 |
| Legacy / Test Support | 12 | 5,006 | 4,441 |
| 合计 | 170 | 193,362 | 182,208 |

## 音频设备与浏览器 I/O

设备选择、麦克风采集、AudioWorklet、播放停止及浏览器所有权。保留在 Web；不能由 Python Agent SDK 替代。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts) | 3,129 | 2,978 | browserAudioIOAdapter |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js) | 203 | 195 | liveVoiceCaptureProcessor |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioPort.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioPort.ts) | 364 | 334 | audioPort |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserAudioDeviceSelection.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserAudioDeviceSelection.ts) | 534 | 494 | browserAudioDeviceSelection |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserLiveVoiceOwnership.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserLiveVoiceOwnership.ts) | 426 | 387 | browserLiveVoiceOwnership |

## Speech Recognition / Synthesis

P1/Cascade 的识别与合成、batch/streaming Port、Provider 适配与取消。SR/SS 共用文件统一计数，不能把同一文件重复算两次。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechRecognitionAdapter.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechRecognitionAdapter.ts) | 117 | 105 | browserSpeechRecognitionAdapter |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechSynthesisAdapter.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechSynthesisAdapter.ts) | 178 | 163 | browserSpeechSynthesisAdapter |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts) | 1,441 | 1,377 | gatewayBatchSpeechClient |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts) | 150 | 142 | integratedP1Route |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts) | 4,440 | 4,313 | productP1VoiceRoute |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceStreamingSpeech.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceStreamingSpeech.ts) | 321 | 280 | liveVoiceStreamingSpeech |
| [jiuwenswarm/server/live_voice/batch_speech.py](../../jiuwenswarm/server/live_voice/batch_speech.py) | 2,745 | 2,572 | Formal batch speech service and dependency-injected Provider Adapter. |
| [jiuwenswarm/server/live_voice/openai_streaming_speech.py](../../jiuwenswarm/server/live_voice/openai_streaming_speech.py) | 2,921 | 2,695 | Default-off OpenAI streaming Speech Adapter and degradation seam. |
| [jiuwenswarm/server/live_voice/speech_ports.py](../../jiuwenswarm/server/live_voice/speech_ports.py) | 477 | 420 | Provider-neutral deterministic speech recognition and synthesis ports. |
| [jiuwenswarm/server/live_voice/streaming_speech.py](../../jiuwenswarm/server/live_voice/streaming_speech.py) | 2,255 | 2,043 | Provider-neutral conformance boundary for native streaming Speech. |

## Realtime Media

浏览器—Gateway 的上下行、注册、帧/ACK、背压、Native RPC 和预制通知音频。保留数据面，压缩装配层。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts) | 1,455 | 1,390 | browserDedicatedMediaRoute |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserGatewayMediaTransport.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserGatewayMediaTransport.ts) | 1,642 | 1,553 | browserGatewayMediaTransport |
| [jiuwenswarm/gateway/live_voice/__init__.py](../../jiuwenswarm/gateway/live_voice/__init__.py) | 3 | 2 | Package-local Live Voice Gateway adapters. |
| [jiuwenswarm/gateway/live_voice/browser_gateway_media_transport.py](../../jiuwenswarm/gateway/live_voice/browser_gateway_media_transport.py) | 1,437 | 1,298 | Provider-neutral Browser <-> Gateway realtime media transport seam. |
| [jiuwenswarm/gateway/live_voice/dedicated_media_registration.py](../../jiuwenswarm/gateway/live_voice/dedicated_media_registration.py) | 8,598 | 8,300 | Central, default-off registration for the formal dedicated media route. |
| [jiuwenswarm/gateway/live_voice/dedicated_media_route.py](../../jiuwenswarm/gateway/live_voice/dedicated_media_route.py) | 1,869 | 1,737 | Package-local proof seam for a dedicated same-origin media route. |
| [jiuwenswarm/gateway/live_voice/native_interaction_runtime_client.py](../../jiuwenswarm/gateway/live_voice/native_interaction_runtime_client.py) | 1,273 | 1,204 | Gateway-only client for the three closed Native Runtime E2A methods. |
| [jiuwenswarm/gateway/live_voice/native_response_downlink.py](../../jiuwenswarm/gateway/live_voice/native_response_downlink.py) | 311 | 281 | Bounded response-scoped Native audio source for dedicated media. |
| [jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py](../../jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py) | 212 | 183 | Exact product bridge from streaming TTS route ownership to media frames. |
| [jiuwenswarm/gateway/live_voice/speech_rpc.py](../../jiuwenswarm/gateway/live_voice/speech_rpc.py) | 142 | 129 | Gateway-local RPC surface for formal SR-B/SS-B batch speech. |
| [jiuwenswarm/gateway/live_voice/streaming_speech_route.py](../../jiuwenswarm/gateway/live_voice/streaming_speech_route.py) | 1,536 | 1,453 | Bounded product owner for one dedicated-media streaming STT route. |
| [jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py](../../jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py) | 2,449 | 2,295 | Bounded product owner for one native-streaming TTS route. |
| [jiuwenswarm/gateway/live_voice/task_notification_preparation.py](../../jiuwenswarm/gateway/live_voice/task_notification_preparation.py) | 327 | 294 | Bounded, unpresented PCM owned by one exact terminal notification. |

## Conversation / Presentation

Turn/Response/generation、打断、已播放事实和历史写入资格。业务执行完成与听到结果是两种状态。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/server/live_voice/conversation_runtime.py](../../jiuwenswarm/server/live_voice/conversation_runtime.py) | 686 | 629 | Canonical in-memory conversation state for the Live Voice formal path. |
| [jiuwenswarm/server/live_voice/conversation_runtime_loop.py](../../jiuwenswarm/server/live_voice/conversation_runtime_loop.py) | 1,559 | 1,420 | Priority event loop and declarative effect outbox for Live Voice CR-B. |
| [jiuwenswarm/server/live_voice/formal_history_writer.py](../../jiuwenswarm/server/live_voice/formal_history_writer.py) | 279 | 259 | Idempotent Session History writer for CR-selected formal text facts. |
| [jiuwenswarm/server/live_voice/native_interaction_runtime.py](../../jiuwenswarm/server/live_voice/native_interaction_runtime.py) | 1,651 | 1,566 | Conversation Runtime authority owner for Native Realtime proposals. |
| [jiuwenswarm/server/live_voice/p2_response_generation_store.py](../../jiuwenswarm/server/live_voice/p2_response_generation_store.py) | 436 | 410 | Durable bounded owner for formal P2 response generations. |
| [jiuwenswarm/server/live_voice/presentation_ledger.py](../../jiuwenswarm/server/live_voice/presentation_ledger.py) | 1,272 | 1,171 | In-memory presentation truth for the Live Voice CR-B runtime. |
| [jiuwenswarm/server/live_voice/progress_notification_arbiter.py](../../jiuwenswarm/server/live_voice/progress_notification_arbiter.py) | 2,228 | 2,093 | Bounded WorkProgress notification arbitration for Conversation Runtime. |
| [jiuwenswarm/server/live_voice/task_event_subscription.py](../../jiuwenswarm/server/live_voice/task_event_subscription.py) | 1,568 | 1,498 | Authorized delivery of canonical formal TaskEvents. |
| [jiuwenswarm/server/live_voice/task_progress_return.py](../../jiuwenswarm/server/live_voice/task_progress_return.py) | 2,291 | 2,151 | Source-backed formal Task progress return without lifecycle authority. |

## Native Provider / Interaction

Realtime Provider 会话、事件映射、Native 参数、提案/载体契约、前台寿命及 continuation。保留语音专有语义。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/server/live_voice/interaction_engine.py](../../jiuwenswarm/server/live_voice/interaction_engine.py) | 602 | 547 | Capability-checked interaction intentions without lifecycle ownership. |
| [jiuwenswarm/server/live_voice/native_continuation_preparation.py](../../jiuwenswarm/server/live_voice/native_continuation_preparation.py) | 488 | 456 | Bounded, authority-free storage for one unpublished Provider continuation. |
| [jiuwenswarm/server/live_voice/native_foreground.py](../../jiuwenswarm/server/live_voice/native_foreground.py) | 85 | 68 | Exact Native foreground cancellation; never authority to cancel a business Task. |
| [jiuwenswarm/server/live_voice/native_interaction_carrier.py](../../jiuwenswarm/server/live_voice/native_interaction_carrier.py) | 526 | 489 | Closed JSON carrier values for Gateway-to-AgentServer Native proposals. |
| [jiuwenswarm/server/live_voice/native_interaction_config.py](../../jiuwenswarm/server/live_voice/native_interaction_config.py) | 241 | 208 | Closed environment selection for Cascade versus Native interaction. |
| [jiuwenswarm/server/live_voice/native_interaction_contract.py](../../jiuwenswarm/server/live_voice/native_interaction_contract.py) | 852 | 771 | Closed, authority-free values for native Live Voice interactions. |
| [jiuwenswarm/server/live_voice/openai_realtime_native_engine.py](../../jiuwenswarm/server/live_voice/openai_realtime_native_engine.py) | 4,181 | 3,999 | Authority-free OpenAI Realtime Native interaction event mapper. |
| [jiuwenswarm/server/live_voice/openai_realtime_session.py](../../jiuwenswarm/server/live_voice/openai_realtime_session.py) | 1,254 | 1,138 | Bounded lifecycle owner for one official OpenAI Realtime WebSocket. |

## Agent Bridge / Work

真实 Agent 轮次接入、输出适配、只读 Work、journal 与 speculative dialogue。优先复用共享执行服务，保留语音投影。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/server/live_voice/agent_bridge.py](../../jiuwenswarm/server/live_voice/agent_bridge.py) | 105 | 88 | Committed-turn-only asynchronous Agent bridge port. |
| [jiuwenswarm/server/live_voice/agent_bridge_runtime.py](../../jiuwenswarm/server/live_voice/agent_bridge_runtime.py) | 1,240 | 1,154 | Bounded non-blocking Agent Bridge runtime for authoritative round progress. |
| [jiuwenswarm/server/live_voice/agent_conversation_runtime.py](../../jiuwenswarm/server/live_voice/agent_conversation_runtime.py) | 5,103 | 4,856 | Product-consumable Agent Bridge + Conversation Runtime composition seam. |
| [jiuwenswarm/server/live_voice/jiuwenswarm_agent_adapter.py](../../jiuwenswarm/server/live_voice/jiuwenswarm_agent_adapter.py) | 106 | 94 | Compatibility Adapter for an already-committed Harness round handle. |
| [jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py](../../jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py) | 1,151 | 1,071 | Harness-owned round reservation, lifecycle, and exact cancellation. |
| [jiuwenswarm/server/live_voice/native_agent_model.py](../../jiuwenswarm/server/live_voice/native_agent_model.py) | 128 | 101 | Closed, credential-free Native Agent model selection and confirmation values. |
| [jiuwenswarm/server/live_voice/native_work_journal.py](../../jiuwenswarm/server/live_voice/native_work_journal.py) | 823 | 787 | Native work checkpoints and recovery facts in the input journal DB. |
| [jiuwenswarm/server/live_voice/native_work_runtime.py](../../jiuwenswarm/server/live_voice/native_work_runtime.py) | 959 | 903 | Bounded, service-owned Native analysis; speech responses own no work lifetime. |
| [jiuwenswarm/server/live_voice/speculative_dialogue.py](../../jiuwenswarm/server/live_voice/speculative_dialogue.py) | 459 | 404 | Speculative dialogue inference: model work before the decision, no effects. |
| [jiuwenswarm/server/runtime/agent_adapter/background_task_checkpoint.py](../../jiuwenswarm/server/runtime/agent_adapter/background_task_checkpoint.py) | 181 | 153 | Process-local Executor checkpoint binding; never supplied by a model/request. |
| [jiuwenswarm/server/runtime/agent_adapter/formal_live_voice.py](../../jiuwenswarm/server/runtime/agent_adapter/formal_live_voice.py) | 401 | 369 | Immutable inputs for the Live Voice formal Agent execution seam. |
| [jiuwenswarm/server/runtime/agent_adapter/formal_model_diagnostics.py](../../jiuwenswarm/server/runtime/agent_adapter/formal_model_diagnostics.py) | 320 | 295 | Content-free observation at the isolated formal Model's client boundary. |

## Task Core / Store

正式 Task/Attempt/Command/Event、SQLite/outbox、调整截止与 successor、持久化/replay。应成为 JiuwenSwarm 通用任务服务。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/server/live_voice/formal_task_models.py](../../jiuwenswarm/server/runtime/formal_tasks/formal_task_models.py) | 2,648 | 2,458 | Formal P3-alpha task records shared by the persistent Core and Executor. |
| [jiuwenswarm/server/live_voice/persistent_task_core.py](../../jiuwenswarm/server/runtime/formal_tasks/persistent_task_core.py) | 1,645 | 1,578 | Formal persistent P3 Task Core and durable outbox orchestration. |
| [jiuwenswarm/server/live_voice/task_adjustment_queue.py](../../jiuwenswarm/server/runtime/formal_tasks/task_adjustment_queue.py) | 352 | 328 | Durable cutover from a running adjustment to an immutable Task revision. |
| [jiuwenswarm/server/live_voice/task_core.py](../../jiuwenswarm/server/live_voice/task_core.py) | 714 | 658 | Deterministic P3-alpha Task Core with replay and exact authorization. |
| [jiuwenswarm/server/live_voice/task_store.py](../../jiuwenswarm/server/runtime/formal_tasks/task_store.py) | 15,224 | 14,890 | SQLite authority for formal P3 command/task/event/attempt state. |

## Executor / Durability

项目执行、文件效果限制、checkpoint/effect、恢复事实和能力声明。Host 文件策略与 SDK 执行原语分层。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/server/live_voice/durability_authority.py](../../jiuwenswarm/server/runtime/durability/durability_authority.py) | 229 | 204 | Opaque, one-operation durability mutation authorization. |
| [jiuwenswarm/server/live_voice/durability_checkpoint.py](../../jiuwenswarm/server/runtime/durability/durability_checkpoint.py) | 499 | 457 | Pure canonical D1 checkpoint value and codec. |
| [jiuwenswarm/server/live_voice/durability_effects.py](../../jiuwenswarm/server/runtime/durability/durability_effects.py) | 920 | 826 | Pure D2 external-effect facts, codec, and reconciliation decision. |
| [jiuwenswarm/server/live_voice/durability_identity.py](../../jiuwenswarm/server/runtime/durability/durability_identity.py) | 150 | 128 | Authority-free identity values shared by pure durability assets. |
| [jiuwenswarm/server/live_voice/durability_readers.py](../../jiuwenswarm/server/runtime/durability/durability_readers.py) | 689 | 628 | Schema-neutral verified prefix readers for caller-owned durability rows. |
| [jiuwenswarm/server/live_voice/durability_recovery_facts.py](../../jiuwenswarm/server/runtime/durability/durability_recovery_facts.py) | 466 | 422 | Canonical authority-free Executor recovery generation facts. |
| [jiuwenswarm/server/live_voice/executor_capabilities.py](../../jiuwenswarm/server/runtime/formal_tasks/executor_capabilities.py) | 373 | 330 | Immutable Executor capability declarations and deterministic selection. |
| [jiuwenswarm/server/live_voice/file_effect_plan.py](../../jiuwenswarm/server/runtime/formal_tasks/file_effect_plan.py) | 416 | 369 | A frozen restriction on an authorized Task's file effects, never a grant. |
| [jiuwenswarm/server/live_voice/project_code_executor.py](../../jiuwenswarm/server/runtime/formal_tasks/project_code_executor.py) | 7,092 | 6,779 | Formal attempt adapters for the bounded project Code Agent. |

## Task Semantics / Business Bridge

已提交输入、模型语义、目标/授权/确认、Native 工具提案、Task/Work 状态查询映射。移出通用部分，保留语音入口。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/server/live_voice/critical_token_safety.py](../../jiuwenswarm/server/live_voice/critical_token_safety.py) | 1,397 | 1,278 | Deterministic critical-token clarification and committed-route guard. |
| [jiuwenswarm/server/live_voice/native_business_context.py](../../jiuwenswarm/server/live_voice/native_business_context.py) | 115 | 97 | Bounded Native conversation facts selected after authenticated scope checks. |
| [jiuwenswarm/server/live_voice/native_business_contract.py](../../jiuwenswarm/server/live_voice/native_business_contract.py) | 251 | 223 | Versioned Native business proposals, never execution or consent receipts. |
| [jiuwenswarm/server/live_voice/native_business_encoding.py](../../jiuwenswarm/server/live_voice/native_business_encoding.py) | 53 | 40 | Lossless string encoding for an already-authorized Native Provider receipt. |
| [jiuwenswarm/server/live_voice/native_business_instructions.py](../../jiuwenswarm/server/live_voice/native_business_instructions.py) | 127 | 103 | Native business wording only; runtime owns tools, scheduling and heard delivery. |
| [jiuwenswarm/server/live_voice/native_business_observation.py](../../jiuwenswarm/server/live_voice/native_business_observation.py) | 114 | 97 | Closed private Native observation and Provider receipt representations. |
| [jiuwenswarm/server/live_voice/native_business_router.py](../../jiuwenswarm/server/live_voice/native_business_router.py) | 725 | 686 | Authenticated structured Native calls into existing Task and Agent owners. |
| [jiuwenswarm/server/live_voice/native_business_tools.py](../../jiuwenswarm/server/live_voice/native_business_tools.py) | 209 | 190 | Operation-specific Provider inputs for the existing Native business carrier. |
| [jiuwenswarm/server/live_voice/native_task_source.py](../../jiuwenswarm/server/live_voice/native_task_source.py) | 177 | 154 | Server-retained speech evidence, distinct from a model's Task proposal. |
| [jiuwenswarm/server/live_voice/p3_confirmation.py](../../jiuwenswarm/server/live_voice/p3_confirmation.py) | 985 | 912 | Server-owned, durable confirmation authority for P3-alpha mutations. |
| [jiuwenswarm/server/live_voice/p3_model_resolution.py](../../jiuwenswarm/server/live_voice/p3_model_resolution.py) | 222 | 201 | Exact, drift-detecting server model resolution for formal P3 tasks. |
| [jiuwenswarm/server/live_voice/p3_product_confirmation.py](../../jiuwenswarm/server/live_voice/p3_product_confirmation.py) | 127 | 109 | Current-owner forwarding permit for product P3 mutation calls. |
| [jiuwenswarm/server/live_voice/p3_production_intent_composition.py](../../jiuwenswarm/server/live_voice/p3_production_intent_composition.py) | 882 | 826 | Authenticated product composition for generalized P3 Task intents. |
| [jiuwenswarm/server/live_voice/production_task_classifier.py](../../jiuwenswarm/server/live_voice/production_task_classifier.py) | 162 | 147 | Closed structured controls. Natural language uses task_semantics only. |
| [jiuwenswarm/server/live_voice/production_task_intent.py](../../jiuwenswarm/server/live_voice/production_task_intent.py) | 2,026 | 1,895 | Trusted production policy for generalized multi-Task intent resolution. |
| [jiuwenswarm/server/live_voice/semantic_continuity.py](../../jiuwenswarm/server/live_voice/semantic_continuity.py) | 255 | 234 | Bounded pre-command data continuity; no Task/Tool/confirmation authority. |
| [jiuwenswarm/server/live_voice/task_control_presentation.py](../../jiuwenswarm/server/live_voice/task_control_presentation.py) | 174 | 161 | Presentation of canonical control facts; never a language/target classifier. |
| [jiuwenswarm/server/live_voice/task_semantics.py](../../jiuwenswarm/server/live_voice/task_semantics.py) | 1,210 | 1,156 | Model-only semantic proposals; deliberately no Task, Tool or history writer. |
| [jiuwenswarm/server/live_voice/unified_committed_input.py](../../jiuwenswarm/server/live_voice/unified_committed_input.py) | 1,694 | 1,628 | Independent durable replay owner for committed hands-free voice input. |
| [jiuwenswarm/server/live_voice/voice_task_bridge.py](../../jiuwenswarm/server/live_voice/voice_task_bridge.py) | 197 | 173 | Deterministic Task authority bridge; semantics live only in task_semantics. |
| [jiuwenswarm/server/live_voice/voice_task_policy.py](../../jiuwenswarm/server/live_voice/voice_task_policy.py) | 739 | 707 | VB-B policy adapter for formal Task Core commands and queries. |

## Product Composition / Authority

Server 装配、认证、scope/project 解析、P2/P3 激活与关闭、文本投影。拆巨大 Registry，但不增加第二个状态权威。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/server/live_voice/__init__.py](../../jiuwenswarm/server/live_voice/__init__.py) | 3 | 2 | Live Voice server integration package. |
| [jiuwenswarm/server/live_voice/p3_authenticated_composition.py](../../jiuwenswarm/server/live_voice/p3_authenticated_composition.py) | 5,417 | 5,154 | Authenticated, server-resolved P3 product composition. |
| [jiuwenswarm/server/live_voice/product_authority.py](../../jiuwenswarm/server/live_voice/product_authority.py) | 1,302 | 1,182 | Server-owned authority foundation for formal Live Voice composition. |
| [jiuwenswarm/server/live_voice/product_composition_contract.py](../../jiuwenswarm/server/live_voice/product_composition_contract.py) | 424 | 384 | Pure Gate-0 contract for Live Voice product composition. |
| [jiuwenswarm/server/live_voice/product_composition_registry.py](../../jiuwenswarm/server/live_voice/product_composition_registry.py) | 16,162 | 15,716 | AgentServer-owned registration boundary for Live Voice product composition. |
| [jiuwenswarm/server/live_voice/product_composition_root.py](../../jiuwenswarm/server/live_voice/product_composition_root.py) | 459 | 402 | Default-off lifecycle owner for Live Voice product composition. |
| [jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py](../../jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py) | 2,127 | 1,957 | Authority-first product activation seam for P2 and Interaction Intelligence. |
| [jiuwenswarm/server/live_voice/product_p3_text_adapter.py](../../jiuwenswarm/server/live_voice/product_p3_text_adapter.py) | 1,207 | 1,108 | Default-off trusted P3 query and truthful text-progress composition seam. |

## Observability / Diagnostics

内容受限的观测、相关性、OTel 导出、延迟/音频/浏览器诊断。复用基础设施，保留语音领域事件与脱敏。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx) | 105 | 100 | L0OrdinaryChromeBatchPanel |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioDiagnosticJournal.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioDiagnosticJournal.ts) | 109 | 103 | audioDiagnosticJournal |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioDiagnostics.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioDiagnostics.ts) | 428 | 416 | audioDiagnostics |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioTimingDiagnostics.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioTimingDiagnostics.ts) | 148 | 141 | audioTimingDiagnostics |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/l0Measurement.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/l0Measurement.ts) | 390 | 363 | l0Measurement |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts) | 645 | 606 | l0OrdinaryChromeBatch |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts) | 1,598 | 1,506 | liveVoiceObservability |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceRouteTelemetry.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceRouteTelemetry.ts) | 257 | 235 | liveVoiceRouteTelemetry |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/webPlatformDiagnostics.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/webPlatformDiagnostics.ts) | 326 | 301 | webPlatformDiagnostics |
| [jiuwenswarm/common/live_voice_audio_diagnostics.py](../../jiuwenswarm/common/live_voice_audio_diagnostics.py) | 194 | 182 | Bounded passive audio diagnostics, never raw payloads or an authority rail. |
| [jiuwenswarm/common/live_voice_lock_diagnostics.py](../../jiuwenswarm/common/live_voice_lock_diagnostics.py) | 62 | 50 | Bounded passive wait/holder observations for existing asyncio locks. |
| [jiuwenswarm/common/live_voice_profiling.py](../../jiuwenswarm/common/live_voice_profiling.py) | 226 | 199 | Passive local spans. No payloads, global monkey patches or business authority. |
| [jiuwenswarm/server/live_voice/latency_measurement.py](../../jiuwenswarm/server/live_voice/latency_measurement.py) | 1,972 | 1,825 | Content-free L0 latency measurement over production observability facts. |
| [jiuwenswarm/server/live_voice/observability.py](../../jiuwenswarm/server/live_voice/observability.py) | 1,960 | 1,810 | Fail-safe correlated observability primitives for Live Voice. |
| [jiuwenswarm/server/live_voice/observability_correlation_contract.py](../../jiuwenswarm/server/live_voice/observability_correlation_contract.py) | 876 | 801 | Pure, content-free correlation contracts for Live Voice diagnostics. |
| [jiuwenswarm/server/live_voice/observability_exporter.py](../../jiuwenswarm/server/live_voice/observability_exporter.py) | 734 | 632 | Bounded asynchronous export isolation for Live Voice observations. |
| [jiuwenswarm/server/live_voice/observability_otel_codec.py](../../jiuwenswarm/server/live_voice/observability_otel_codec.py) | 641 | 584 | Pure OTel backend codec for current Live Voice observability facts. |
| [jiuwenswarm/server/live_voice/product_observability_adapter.py](../../jiuwenswarm/server/live_voice/product_observability_adapter.py) | 847 | 737 | Package-only product consumer for governed Live Voice observability facts. |
| [jiuwenswarm/server/live_voice/product_observability_runtime.py](../../jiuwenswarm/server/live_voice/product_observability_runtime.py) | 1,425 | 1,332 | Validated product composition for the Live Voice OTel backend boundary. |
| [jiuwenswarm/server/live_voice/speech_http_diagnostics.py](../../jiuwenswarm/server/live_voice/speech_http_diagnostics.py) | 63 | 56 | Passive HTTP phase observation; never retain httpcore trace info or content. |
| [jiuwenswarm/server/live_voice/speech_socket_diagnostics.py](../../jiuwenswarm/server/live_voice/speech_socket_diagnostics.py) | 239 | 214 | Passive, content-free recognition send/flow-control observations. |

## Protocol / Shared Contract

Python/TypeScript wire 模型、错误与消息契约。统一 schema 来源，保留各信任边界验证。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceContractV2.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceContractV2.ts) | 2,785 | 2,627 | liveVoiceContractV2 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productCompositionContract.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productCompositionContract.ts) | 289 | 273 | productCompositionContract |
| [jiuwenswarm/common/schema/live_voice_contract.py](../../jiuwenswarm/common/schema/live_voice_contract.py) | 235 | 184 | Minimal, dependency-free contract gate for Live Voice shared events. |
| [jiuwenswarm/common/schema/live_voice_contract_v2.py](../../jiuwenswarm/common/schema/live_voice_contract_v2.py) | 4,002 | 3,692 | Pure critical-kernel primitives for ``live-voice.contract.v2``. |

## Web Product / Task UI

产品语音面板、任务控制/结果、激活 journal、Web 交互集成。归 JiuwenSwarm Web feature。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.css](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.css) | 754 | 651 | LiveVoiceDemoBar |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx) | 637 | 613 | LiveVoiceDemoBar |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.css](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.css) | 188 | 161 | LiveVoiceIntegratedRoutePanel |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx) | 9,943 | 9,743 | LiveVoiceIntegratedRoutePanel |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/productTaskProgressPresentation.ts](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/productTaskProgressPresentation.ts) | 8 | 8 | productTaskProgressPresentation |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts) | 261 | 249 | useProductVoiceBrowserOwnership |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceSessionStart.ts](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceSessionStart.ts) | 99 | 93 | useProductVoiceSessionStart |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalP3TaskExperience.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalP3TaskExperience.ts) | 972 | 915 | formalP3TaskExperience |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskControlLeaf.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskControlLeaf.ts) | 952 | 914 | formalTaskControlLeaf |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskIntentRoute.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskIntentRoute.ts) | 995 | 954 | formalTaskIntentRoute |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskResultRoute.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskResultRoute.ts) | 311 | 288 | formalTaskResultRoute |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts) | 587 | 541 | integratedWebRouteShell |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/nativeGeneratedText.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/nativeGeneratedText.ts) | 54 | 50 | nativeGeneratedText |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/nativeWorkState.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/nativeWorkState.ts) | 66 | 64 | nativeWorkState |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP2ActivationJournal.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP2ActivationJournal.ts) | 1,314 | 1,246 | productP2ActivationJournal |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3ProgressGenerationJournal.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3ProgressGenerationJournal.ts) | 236 | 220 | productP3ProgressGenerationJournal |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3TaskTargetJournal.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3TaskTargetJournal.ts) | 148 | 137 | productP3TaskTargetJournal |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productTextProgress.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productTextProgress.ts) | 870 | 827 | productTextProgress |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts) | 2,223 | 2,113 | productWebActivation |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/taskNotificationIdentity.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/taskNotificationIdentity.ts) | 47 | 43 | taskNotificationIdentity |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/unifiedCommittedInputOwner.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/unifiedCommittedInputOwner.ts) | 299 | 283 | unifiedCommittedInputOwner |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceCore.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceCore.ts) | 445 | 380 | liveVoiceCore |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceMessageGate.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceMessageGate.ts) | 119 | 107 | liveVoiceMessageGate |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTurnLifecycle.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTurnLifecycle.ts) | 256 | 233 | liveVoiceTurnLifecycle |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/taskPresentationView.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/taskPresentationView.ts) | 29 | 29 | taskPresentationView |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts) | 873 | 812 | useLiveVoiceDemo |
| [jiuwenswarm/channels/web/frontend/src/multi-session/state/createLiveVoiceConversation.ts](../../jiuwenswarm/channels/web/frontend/src/multi-session/state/createLiveVoiceConversation.ts) | 55 | 53 | createLiveVoiceConversation |
| [jiuwenswarm/channels/web/frontend/src/stores/liveVoiceTaskStore.ts](../../jiuwenswarm/channels/web/frontend/src/stores/liveVoiceTaskStore.ts) | 42 | 39 | liveVoiceTaskStore |

## Configuration / Deployment

配置声明、运行环境和部署预检。归应用配置/运维工具，不进入 AgentCore。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/channels/web/live_voice_deployment_observer.py](../../jiuwenswarm/channels/web/live_voice_deployment_observer.py) | 1,045 | 956 | Bounded, credential-free runtime observation for a Live Voice deployment. |
| [jiuwenswarm/channels/web/live_voice_deployment_preflight.py](../../jiuwenswarm/channels/web/live_voice_deployment_preflight.py) | 449 | 392 | Pure configuration preflight for a Live Voice Web deployment. |
| [jiuwenswarm/common/live_voice_capture_limits.py](../../jiuwenswarm/common/live_voice_capture_limits.py) | 10 | 8 | Transport bounds for the existing Web P1 capture, not semantic policy. |
| [jiuwenswarm/common/live_voice_operation_budgets.py](../../jiuwenswarm/common/live_voice_operation_budgets.py) | 21 | 17 | Failure ceilings for the sole semantic path, not intended response latency. |
| [jiuwenswarm/server/live_voice/live_voice_configuration_declaration.py](../../jiuwenswarm/server/live_voice/live_voice_configuration_declaration.py) | 1,003 | 917 | Pure validated-configuration to capability-declaration contract. |

## Legacy / Test Support

静态生产引用检查未发现调用的验证/fake/旧原型。先迁移有效测试断言，再退出生产包。

| 文件 | 物理行 | 非空行 | 代码职责 / 入口 |
|---|---:|---:|---|
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/conversationRuntimeReplica.ts](../../jiuwenswarm/channels/web/frontend/tests/support/live_voice/conversationRuntimeReplica.ts) | 258 | 238 | conversationRuntimeReplica |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/fakeP1Vertical.ts](../../jiuwenswarm/channels/web/frontend/tests/support/live_voice/fakeP1Vertical.ts) | 104 | 94 | fakeP1Vertical |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/webLifecycleObservationRecorder.ts](../../jiuwenswarm/channels/web/frontend/tests/support/live_voice/webLifecycleObservationRecorder.ts) | 383 | 357 | webLifecycleObservationRecorder |
| [jiuwenswarm/server/live_voice/alpha_benchmark.py](../../tests/support/live_voice/alpha_benchmark.py) | 633 | 564 | Deterministic, evidence-bounded Live Voice Alpha benchmark summaries. |
| [jiuwenswarm/server/live_voice/alpha_privacy_conformance.py](../../tests/support/live_voice/alpha_privacy_conformance.py) | 1,025 | 899 | Bounded synthetic-canary checks for Live Voice Alpha privacy surfaces. |
| [jiuwenswarm/server/live_voice/executor_port.py](../../tests/support/live_voice/executor_port.py) | 117 | 95 | Truthful deterministic executor port for P3-alpha attempts. |
| [jiuwenswarm/server/live_voice/fake_verticals.py](../../tests/support/live_voice/fake_verticals.py) | 404 | 370 | Deterministic P1, P2, and P3-alpha integration verticals. |
| [jiuwenswarm/server/live_voice/observability_fault_harness.py](../../tests/support/live_voice/observability_fault_harness.py) | 391 | 325 | Bounded, payload-free fault exporter for Live Voice observability tests. |
| [jiuwenswarm/server/live_voice/product_p2_readiness.py](../../tests/support/live_voice/product_p2_readiness.py) | 262 | 219 | Pure dependency-readiness evaluator for the product P2 browser journey. |
| [jiuwenswarm/server/live_voice/realtime_media.py](../../tests/support/live_voice/realtime_media.py) | 822 | 742 | Bounded, conversation-neutral realtime media port. |
| [jiuwenswarm/server/live_voice/sli_window_contract.py](../../tests/support/live_voice/sli_window_contract.py) | 386 | 351 | Content-free SLI window arithmetic for P3 diagnostics. |
| [jiuwenswarm/server/live_voice/telemetry_privacy_contract.py](../../tests/support/live_voice/telemetry_privacy_contract.py) | 221 | 187 | Declaration-only privacy vocabulary for P3 telemetry composition. |

## 共享接入面：不可整文件计入 Live Voice

这些文件包含真实接入或兼容关系；需要随接口变更回归，但不能把原有 Chat、Agent、TTS、历史和 AutoHarness 功能整体删除。

| 文件 | 整文件行数（不纳入上述专用代码合计） |
|---|---:|
| [jiuwenswarm/agents/harness/common/auto_harness/scheduler.py](../../jiuwenswarm/agents/harness/common/auto_harness/scheduler.py) | 843 |
| [jiuwenswarm/agents/harness/common/auto_harness/service.py](../../jiuwenswarm/agents/harness/common/auto_harness/service.py) | 4,209 |
| [jiuwenswarm/agents/harness/common/auto_harness/task_store.py](../../jiuwenswarm/agents/harness/common/auto_harness/task_store.py) | 773 |
| [jiuwenswarm/agents/harness/common/rails/response_prompt_rail.py](../../jiuwenswarm/agents/harness/common/rails/response_prompt_rail.py) | 222 |
| [jiuwenswarm/channels/web/app_web.py](../../jiuwenswarm/channels/web/app_web.py) | 1,484 |
| [jiuwenswarm/channels/web/frontend/src/App.tsx](../../jiuwenswarm/channels/web/frontend/src/App.tsx) | 2,768 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/MessageItem.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/MessageItem.tsx) | 930 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx) | 1,645 |
| [jiuwenswarm/channels/web/frontend/src/components/ToolPanel/RecentTasksPanel.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ToolPanel/RecentTasksPanel.tsx) | 70 |
| [jiuwenswarm/channels/web/frontend/src/components/ToolPanel/index.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ToolPanel/index.tsx) | 597 |
| [jiuwenswarm/channels/web/frontend/src/services/webClient.ts](../../jiuwenswarm/channels/web/frontend/src/services/webClient.ts) | 673 |
| [jiuwenswarm/channels/web/frontend/src/stores/chatStore.ts](../../jiuwenswarm/channels/web/frontend/src/stores/chatStore.ts) | 1,836 |
| [jiuwenswarm/channels/web/frontend/src/types/message.ts](../../jiuwenswarm/channels/web/frontend/src/types/message.ts) | 152 |
| [jiuwenswarm/channels/web/frontend/src/utils/tts.ts](../../jiuwenswarm/channels/web/frontend/src/utils/tts.ts) | 150 |
| [jiuwenswarm/channels/web/frontend/src/utils/ttsOutputOwnership.ts](../../jiuwenswarm/channels/web/frontend/src/utils/ttsOutputOwnership.ts) | 40 |
| [jiuwenswarm/channels/web/frontend/src/utils/ttsText.ts](../../jiuwenswarm/channels/web/frontend/src/utils/ttsText.ts) | 113 |
| [jiuwenswarm/common/e2a/wire_codec.py](../../jiuwenswarm/common/e2a/wire_codec.py) | 483 |
| [jiuwenswarm/common/schema/message.py](../../jiuwenswarm/common/schema/message.py) | 385 |
| [jiuwenswarm/gateway/app_gateway.py](../../jiuwenswarm/gateway/app_gateway.py) | 3,257 |
| [jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py](../../jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py) | 6,720 |
| [jiuwenswarm/gateway/channel_manager/web/web_connect.py](../../jiuwenswarm/gateway/channel_manager/web/web_connect.py) | 1,878 |
| [jiuwenswarm/gateway/routing/agent_client.py](../../jiuwenswarm/gateway/routing/agent_client.py) | 1,026 |
| [jiuwenswarm/server/agent_ws_server.py](../../jiuwenswarm/server/agent_ws_server.py) | 9,948 |
| [jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py](../../jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py) | 168 |
| [jiuwenswarm/server/runtime/agent_adapter/interface.py](../../jiuwenswarm/server/runtime/agent_adapter/interface.py) | 3,566 |
| [jiuwenswarm/server/runtime/agent_adapter/interface_deep.py](../../jiuwenswarm/server/runtime/agent_adapter/interface_deep.py) | 12,598 |
| [jiuwenswarm/server/runtime/agent_manager.py](../../jiuwenswarm/server/runtime/agent_manager.py) | 1,459 |
| [jiuwenswarm/server/runtime/session/session_history.py](../../jiuwenswarm/server/runtime/session/session_history.py) | 808 |

## 测试、脚本与文档的独立体量

下面是名称/目录匹配清单，不是全依赖闭包。前端部分 product* 测试位于普通 tests 路径，不能因名字不含 liveVoice 就漏掉迁移检查。fixtures 的 JSON 是测试数据，不是生产代码。

| 集合 | 文件数 | 物理行 |
|---|---:|---:|
| 后端 tests 内名称/目录匹配 | 170 | 156,399 |
| 前端 tests 内名称/目录匹配 | 34 | 37,664 |
| scripts 内名称/目录匹配（含 JSON、嵌套测试） | 35 | 18,935 |
| live-voice 文档/证据目录 | 242 | 49,837 |

## 统计复核方法

用 `git ls-files` 限定跟踪文件，对专用目录和文件名匹配 `live_voice / liveVoice / live-voice`；补上上文六个由引用搜索发现的专用文件。UTF-8 解码后用 `splitlines()` 计物理行、`line.strip()` 计非空行。Python 使用 `ast.parse` 检查文件结构并提取类/函数范围；进口图包含普通及相对 import，随后通过 `rg` 复核动态加载、类型引用和测试脚本。路径清单本身就是可复核的统计范围。

对候选删除还必须检查 string-based import、注册表、命令入口、构建配置与唯一测试断言。本清单没有以“未运行到”替代这些检查，也没有把静态无生产调用认定为不需要任何测试。
