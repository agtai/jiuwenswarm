# Live Voice 瘦身后的代码量（2026-09-11）

比较基线：`537c5d2c9fc595fe38b2ccd1f93b8984fce594a3`；实现快照：`ea449432`（诊断文件末尾空行在报告提交中清理）。物理行包含空行、注释；不是 SLOC、性能或质量指标。

以原审计 170 个文件为固定起点，沿 retirement manifest 的两个 relocation 映射追踪，再计入本次拆出的四个 Voice 文件及三个测试类文件。Host 新共享执行模块在下一表单列。测试支撑不算生产代码；移目录不算净删除。

| 模块（原审计归属） | 基线行数 | 当前 Voice 专有 | 已归 Host | 已归测试支撑 |
|---|---:|---:|---:|---:|
| Web Product / Task UI | 22,783 | 23,017 | 0 | 0 |
| 音频设备与浏览器 I/O | 4,656 | 4,656 | 0 | 0 |
| Realtime Media | 21,254 | 21,254 | 0 | 0 |
| Speech Recognition / Synthesis | 15,045 | 15,045 | 0 | 0 |
| Observability / Diagnostics | 13,245 | 13,841 | 0 | 0 |
| Legacy / Test Support | 5,006 | 0 | 0 | 6,336 |
| Protocol / Shared Contract | 7,311 | 7,311 | 0 | 0 |
| Configuration / Deployment | 2,528 | 2,528 | 0 | 0 |
| Product Composition / Authority | 27,101 | 26,563 | 0 | 0 |
| Agent Bridge / Work | 10,976 | 10,552 | 0 | 0 |
| Conversation / Presentation | 11,970 | 11,970 | 0 | 0 |
| Task Semantics / Business Bridge | 11,841 | 11,811 | 0 | 0 |
| Executor / Durability | 10,834 | 0 | 10,341 | 0 |
| Task Core / Store | 20,583 | 211 | 19,869 | 0 |
| Native Provider / Interaction | 8,229 | 7,977 | 0 | 0 |
| 合计 | 193,362 | 156,736 | 30,210 | 6,336 |

后端 `server/live_voice`：92 文件 / **123,051 → 86,857 行**（72 文件），目录减少 **36,194 行，29.4%**。其中大量是归属迁移，不能宣传为仓库净删。

统一生产源码口径：Git 跟踪的 `jiuwenswarm/` 下 `.py/.ts/.tsx/.js/.mjs/.css`，排除 `/tests/`。相对基线净变化 **-3,021 行**。该口径计入新增共享服务和接口、移走的测试实现及拆文件开销；不含 SDK 外部依赖、文档、测试和构建脚本。

## 新增共享模块（不与上表的迁移模块重复）

| 当前路径 | 行数 |
|---|---:|
| [jiuwenswarm/server/runtime/agent_adapter/stream_history_state.py](../../jiuwenswarm/server/runtime/agent_adapter/stream_history_state.py) | 78 |
| [jiuwenswarm/server/runtime/agent_adapter/stream_source.py](../../jiuwenswarm/server/runtime/agent_adapter/stream_source.py) | 107 |
| [jiuwenswarm/server/runtime/agent_adapter/work_model.py](../../jiuwenswarm/server/runtime/agent_adapter/work_model.py) | 138 |
| [jiuwenswarm/server/runtime/agent_interrupt_execution.py](../../jiuwenswarm/server/runtime/agent_interrupt_execution.py) | 334 |
| [jiuwenswarm/server/runtime/agent_resolution.py](../../jiuwenswarm/server/runtime/agent_resolution.py) | 376 |
| [jiuwenswarm/server/runtime/durability/__init__.py](../../jiuwenswarm/server/runtime/durability/__init__.py) | 1 |
| [jiuwenswarm/server/runtime/execution_context.py](../../jiuwenswarm/server/runtime/execution_context.py) | 167 |
| [jiuwenswarm/server/runtime/formal_tasks/__init__.py](../../jiuwenswarm/server/runtime/formal_tasks/__init__.py) | 1 |
| [jiuwenswarm/server/runtime/session_execution.py](../../jiuwenswarm/server/runtime/session_execution.py) | 722 |
| [jiuwenswarm/server/runtime/team_execution.py](../../jiuwenswarm/server/runtime/team_execution.py) | 583 |
| [jiuwenswarm/server/runtime/team_execution_capabilities.py](../../jiuwenswarm/server/runtime/team_execution_capabilities.py) | 243 |
| [jiuwenswarm/server/runtime/team_workflow_capabilities.py](../../jiuwenswarm/server/runtime/team_workflow_capabilities.py) | 83 |
| [jiuwenswarm/server/runtime/workflow_queries.py](../../jiuwenswarm/server/runtime/workflow_queries.py) | 81 |

## 追踪后的逐文件清单

这里展示落位后的文件与实际行数；原模块解释及基线文件数见原审计。

| 文件 | 归属 | 物理行 |
|---|---|---:|
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx) | Voice 专有边界 | 105 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.css](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.css) | Voice 专有边界 | 754 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx) | Voice 专有边界 | 637 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.css](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.css) | Voice 专有边界 | 188 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx) | Voice 专有边界 | 7,691 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanelView.tsx](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanelView.tsx) | Voice 专有边界 | 535 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/liveVoiceProductOperations.ts](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/liveVoiceProductOperations.ts) | Voice 专有边界 | 1,951 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/productTaskProgressPresentation.ts](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/productTaskProgressPresentation.ts) | Voice 专有边界 | 8 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts) | Voice 专有边界 | 261 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceSessionStart.ts](../../jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceSessionStart.ts) | Voice 专有边界 | 99 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts) | Voice 专有边界 | 3,129 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts) | Voice 专有边界 | 1,455 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserGatewayMediaTransport.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserGatewayMediaTransport.ts) | Voice 专有边界 | 1,642 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechRecognitionAdapter.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechRecognitionAdapter.ts) | Voice 专有边界 | 117 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechSynthesisAdapter.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechSynthesisAdapter.ts) | Voice 专有边界 | 178 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js) | Voice 专有边界 | 203 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioDiagnosticJournal.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioDiagnosticJournal.ts) | Voice 专有边界 | 109 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioDiagnostics.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioDiagnostics.ts) | Voice 专有边界 | 428 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioPort.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioPort.ts) | Voice 专有边界 | 364 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioTimingDiagnostics.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioTimingDiagnostics.ts) | Voice 专有边界 | 148 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserAudioDeviceSelection.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserAudioDeviceSelection.ts) | Voice 专有边界 | 534 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserLiveVoiceOwnership.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserLiveVoiceOwnership.ts) | Voice 专有边界 | 426 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalP3TaskExperience.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalP3TaskExperience.ts) | Voice 专有边界 | 972 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskControlLeaf.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskControlLeaf.ts) | Voice 专有边界 | 952 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskIntentRoute.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskIntentRoute.ts) | Voice 专有边界 | 995 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskResultRoute.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskResultRoute.ts) | Voice 专有边界 | 311 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts) | Voice 专有边界 | 1,441 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts) | Voice 专有边界 | 150 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts) | Voice 专有边界 | 587 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/l0Measurement.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/l0Measurement.ts) | Voice 专有边界 | 390 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts) | Voice 专有边界 | 645 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceContractV2.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceContractV2.ts) | Voice 专有边界 | 2,785 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts) | Voice 专有边界 | 1,598 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceRouteTelemetry.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceRouteTelemetry.ts) | Voice 专有边界 | 257 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/nativeGeneratedText.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/nativeGeneratedText.ts) | Voice 专有边界 | 54 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/nativeWorkState.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/nativeWorkState.ts) | Voice 专有边界 | 66 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productCompositionContract.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productCompositionContract.ts) | Voice 专有边界 | 289 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts) | Voice 专有边界 | 4,440 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP2ActivationJournal.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP2ActivationJournal.ts) | Voice 专有边界 | 1,314 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3ProgressGenerationJournal.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3ProgressGenerationJournal.ts) | Voice 专有边界 | 236 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3TaskTargetJournal.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3TaskTargetJournal.ts) | Voice 专有边界 | 148 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productTextProgress.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productTextProgress.ts) | Voice 专有边界 | 870 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts) | Voice 专有边界 | 2,223 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/taskNotificationIdentity.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/taskNotificationIdentity.ts) | Voice 专有边界 | 47 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/unifiedCommittedInputOwner.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/unifiedCommittedInputOwner.ts) | Voice 专有边界 | 299 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/webPlatformDiagnostics.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/webPlatformDiagnostics.ts) | Voice 专有边界 | 326 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceCore.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceCore.ts) | Voice 专有边界 | 445 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceMessageGate.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceMessageGate.ts) | Voice 专有边界 | 119 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceStreamingSpeech.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceStreamingSpeech.ts) | Voice 专有边界 | 321 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTurnLifecycle.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTurnLifecycle.ts) | Voice 专有边界 | 256 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/taskPresentationView.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/taskPresentationView.ts) | Voice 专有边界 | 29 |
| [jiuwenswarm/channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts) | Voice 专有边界 | 873 |
| [jiuwenswarm/channels/web/frontend/src/multi-session/state/createLiveVoiceConversation.ts](../../jiuwenswarm/channels/web/frontend/src/multi-session/state/createLiveVoiceConversation.ts) | Voice 专有边界 | 55 |
| [jiuwenswarm/channels/web/frontend/src/stores/liveVoiceTaskStore.ts](../../jiuwenswarm/channels/web/frontend/src/stores/liveVoiceTaskStore.ts) | Voice 专有边界 | 42 |
| [jiuwenswarm/channels/web/frontend/tests/support/live_voice/conversationRuntimeReplica.ts](../../jiuwenswarm/channels/web/frontend/tests/support/live_voice/conversationRuntimeReplica.ts) | 测试支撑 | 258 |
| [jiuwenswarm/channels/web/frontend/tests/support/live_voice/fakeP1Vertical.ts](../../jiuwenswarm/channels/web/frontend/tests/support/live_voice/fakeP1Vertical.ts) | 测试支撑 | 104 |
| [jiuwenswarm/channels/web/frontend/tests/support/live_voice/webLifecycleObservationRecorder.ts](../../jiuwenswarm/channels/web/frontend/tests/support/live_voice/webLifecycleObservationRecorder.ts) | 测试支撑 | 383 |
| [jiuwenswarm/channels/web/live_voice_deployment_observer.py](../../jiuwenswarm/channels/web/live_voice_deployment_observer.py) | Voice 专有边界 | 1,045 |
| [jiuwenswarm/channels/web/live_voice_deployment_preflight.py](../../jiuwenswarm/channels/web/live_voice_deployment_preflight.py) | Voice 专有边界 | 449 |
| [jiuwenswarm/common/live_voice_audio_diagnostics.py](../../jiuwenswarm/common/live_voice_audio_diagnostics.py) | Voice 专有边界 | 194 |
| [jiuwenswarm/common/live_voice_capture_limits.py](../../jiuwenswarm/common/live_voice_capture_limits.py) | Voice 专有边界 | 10 |
| [jiuwenswarm/common/live_voice_lock_diagnostics.py](../../jiuwenswarm/common/live_voice_lock_diagnostics.py) | Voice 专有边界 | 62 |
| [jiuwenswarm/common/live_voice_operation_budgets.py](../../jiuwenswarm/common/live_voice_operation_budgets.py) | Voice 专有边界 | 21 |
| [jiuwenswarm/common/live_voice_profiling.py](../../jiuwenswarm/common/live_voice_profiling.py) | Voice 专有边界 | 226 |
| [jiuwenswarm/common/schema/live_voice_contract.py](../../jiuwenswarm/common/schema/live_voice_contract.py) | Voice 专有边界 | 235 |
| [jiuwenswarm/common/schema/live_voice_contract_v2.py](../../jiuwenswarm/common/schema/live_voice_contract_v2.py) | Voice 专有边界 | 4,002 |
| [jiuwenswarm/gateway/live_voice/__init__.py](../../jiuwenswarm/gateway/live_voice/__init__.py) | Voice 专有边界 | 3 |
| [jiuwenswarm/gateway/live_voice/browser_gateway_media_transport.py](../../jiuwenswarm/gateway/live_voice/browser_gateway_media_transport.py) | Voice 专有边界 | 1,437 |
| [jiuwenswarm/gateway/live_voice/dedicated_media_registration.py](../../jiuwenswarm/gateway/live_voice/dedicated_media_registration.py) | Voice 专有边界 | 8,598 |
| [jiuwenswarm/gateway/live_voice/dedicated_media_route.py](../../jiuwenswarm/gateway/live_voice/dedicated_media_route.py) | Voice 专有边界 | 1,869 |
| [jiuwenswarm/gateway/live_voice/native_interaction_runtime_client.py](../../jiuwenswarm/gateway/live_voice/native_interaction_runtime_client.py) | Voice 专有边界 | 1,273 |
| [jiuwenswarm/gateway/live_voice/native_response_downlink.py](../../jiuwenswarm/gateway/live_voice/native_response_downlink.py) | Voice 专有边界 | 311 |
| [jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py](../../jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py) | Voice 专有边界 | 212 |
| [jiuwenswarm/gateway/live_voice/speech_rpc.py](../../jiuwenswarm/gateway/live_voice/speech_rpc.py) | Voice 专有边界 | 142 |
| [jiuwenswarm/gateway/live_voice/streaming_speech_route.py](../../jiuwenswarm/gateway/live_voice/streaming_speech_route.py) | Voice 专有边界 | 1,536 |
| [jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py](../../jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py) | Voice 专有边界 | 2,449 |
| [jiuwenswarm/gateway/live_voice/task_notification_preparation.py](../../jiuwenswarm/gateway/live_voice/task_notification_preparation.py) | Voice 专有边界 | 327 |
| [jiuwenswarm/server/live_voice/__init__.py](../../jiuwenswarm/server/live_voice/__init__.py) | Voice 专有边界 | 3 |
| [jiuwenswarm/server/live_voice/agent_bridge.py](../../jiuwenswarm/server/live_voice/agent_bridge.py) | Voice 专有边界 | 105 |
| [jiuwenswarm/server/live_voice/agent_bridge_runtime.py](../../jiuwenswarm/server/live_voice/agent_bridge_runtime.py) | Voice 专有边界 | 1,240 |
| [jiuwenswarm/server/live_voice/agent_conversation_runtime.py](../../jiuwenswarm/server/live_voice/agent_conversation_runtime.py) | Voice 专有边界 | 4,682 |
| [jiuwenswarm/server/live_voice/batch_speech.py](../../jiuwenswarm/server/live_voice/batch_speech.py) | Voice 专有边界 | 2,745 |
| [jiuwenswarm/server/live_voice/conversation_runtime.py](../../jiuwenswarm/server/live_voice/conversation_runtime.py) | Voice 专有边界 | 686 |
| [jiuwenswarm/server/live_voice/conversation_runtime_loop.py](../../jiuwenswarm/server/live_voice/conversation_runtime_loop.py) | Voice 专有边界 | 1,559 |
| [jiuwenswarm/server/live_voice/critical_token_safety.py](../../jiuwenswarm/server/live_voice/critical_token_safety.py) | Voice 专有边界 | 1,397 |
| [jiuwenswarm/server/live_voice/formal_history_writer.py](../../jiuwenswarm/server/live_voice/formal_history_writer.py) | Voice 专有边界 | 279 |
| [jiuwenswarm/server/live_voice/interaction_engine.py](../../jiuwenswarm/server/live_voice/interaction_engine.py) | Voice 专有边界 | 350 |
| [jiuwenswarm/server/live_voice/jiuwenswarm_agent_adapter.py](../../jiuwenswarm/server/live_voice/jiuwenswarm_agent_adapter.py) | Voice 专有边界 | 106 |
| [jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py](../../jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py) | Voice 专有边界 | 1,034 |
| [jiuwenswarm/server/live_voice/latency_measurement.py](../../jiuwenswarm/server/live_voice/latency_measurement.py) | Voice 专有边界 | 1,972 |
| [jiuwenswarm/server/live_voice/live_voice_configuration_declaration.py](../../jiuwenswarm/server/live_voice/live_voice_configuration_declaration.py) | Voice 专有边界 | 1,003 |
| [jiuwenswarm/server/live_voice/native_agent_model.py](../../jiuwenswarm/server/live_voice/native_agent_model.py) | Voice 专有边界 | 128 |
| [jiuwenswarm/server/live_voice/native_business_context.py](../../jiuwenswarm/server/live_voice/native_business_context.py) | Voice 专有边界 | 115 |
| [jiuwenswarm/server/live_voice/native_business_contract.py](../../jiuwenswarm/server/live_voice/native_business_contract.py) | Voice 专有边界 | 251 |
| [jiuwenswarm/server/live_voice/native_business_encoding.py](../../jiuwenswarm/server/live_voice/native_business_encoding.py) | Voice 专有边界 | 53 |
| [jiuwenswarm/server/live_voice/native_business_instructions.py](../../jiuwenswarm/server/live_voice/native_business_instructions.py) | Voice 专有边界 | 127 |
| [jiuwenswarm/server/live_voice/native_business_observation.py](../../jiuwenswarm/server/live_voice/native_business_observation.py) | Voice 专有边界 | 114 |
| [jiuwenswarm/server/live_voice/native_business_router.py](../../jiuwenswarm/server/live_voice/native_business_router.py) | Voice 专有边界 | 695 |
| [jiuwenswarm/server/live_voice/native_business_tools.py](../../jiuwenswarm/server/live_voice/native_business_tools.py) | Voice 专有边界 | 209 |
| [jiuwenswarm/server/live_voice/native_continuation_preparation.py](../../jiuwenswarm/server/live_voice/native_continuation_preparation.py) | Voice 专有边界 | 488 |
| [jiuwenswarm/server/live_voice/native_foreground.py](../../jiuwenswarm/server/live_voice/native_foreground.py) | Voice 专有边界 | 85 |
| [jiuwenswarm/server/live_voice/native_interaction_carrier.py](../../jiuwenswarm/server/live_voice/native_interaction_carrier.py) | Voice 专有边界 | 526 |
| [jiuwenswarm/server/live_voice/native_interaction_config.py](../../jiuwenswarm/server/live_voice/native_interaction_config.py) | Voice 专有边界 | 241 |
| [jiuwenswarm/server/live_voice/native_interaction_contract.py](../../jiuwenswarm/server/live_voice/native_interaction_contract.py) | Voice 专有边界 | 852 |
| [jiuwenswarm/server/live_voice/native_interaction_runtime.py](../../jiuwenswarm/server/live_voice/native_interaction_runtime.py) | Voice 专有边界 | 1,651 |
| [jiuwenswarm/server/live_voice/native_task_source.py](../../jiuwenswarm/server/live_voice/native_task_source.py) | Voice 专有边界 | 177 |
| [jiuwenswarm/server/live_voice/native_work_journal.py](../../jiuwenswarm/server/live_voice/native_work_journal.py) | Voice 专有边界 | 823 |
| [jiuwenswarm/server/live_voice/native_work_runtime.py](../../jiuwenswarm/server/live_voice/native_work_runtime.py) | Voice 专有边界 | 994 |
| [jiuwenswarm/server/live_voice/observability.py](../../jiuwenswarm/server/live_voice/observability.py) | Voice 专有边界 | 1,960 |
| [jiuwenswarm/server/live_voice/observability_correlation_contract.py](../../jiuwenswarm/server/live_voice/observability_correlation_contract.py) | Voice 专有边界 | 876 |
| [jiuwenswarm/server/live_voice/observability_exporter.py](../../jiuwenswarm/server/live_voice/observability_exporter.py) | Voice 专有边界 | 734 |
| [jiuwenswarm/server/live_voice/observability_otel_codec.py](../../jiuwenswarm/server/live_voice/observability_otel_codec.py) | Voice 专有边界 | 641 |
| [jiuwenswarm/server/live_voice/openai_realtime_native_engine.py](../../jiuwenswarm/server/live_voice/openai_realtime_native_engine.py) | Voice 专有边界 | 4,181 |
| [jiuwenswarm/server/live_voice/openai_realtime_session.py](../../jiuwenswarm/server/live_voice/openai_realtime_session.py) | Voice 专有边界 | 1,254 |
| [jiuwenswarm/server/live_voice/openai_streaming_speech.py](../../jiuwenswarm/server/live_voice/openai_streaming_speech.py) | Voice 专有边界 | 2,921 |
| [jiuwenswarm/server/live_voice/p2_response_generation_store.py](../../jiuwenswarm/server/live_voice/p2_response_generation_store.py) | Voice 专有边界 | 436 |
| [jiuwenswarm/server/live_voice/p3_authenticated_composition.py](../../jiuwenswarm/server/live_voice/p3_authenticated_composition.py) | Voice 专有边界 | 5,417 |
| [jiuwenswarm/server/live_voice/p3_confirmation.py](../../jiuwenswarm/server/live_voice/p3_confirmation.py) | Voice 专有边界 | 985 |
| [jiuwenswarm/server/live_voice/p3_model_resolution.py](../../jiuwenswarm/server/live_voice/p3_model_resolution.py) | Voice 专有边界 | 222 |
| [jiuwenswarm/server/live_voice/p3_product_confirmation.py](../../jiuwenswarm/server/live_voice/p3_product_confirmation.py) | Voice 专有边界 | 127 |
| [jiuwenswarm/server/live_voice/p3_production_intent_composition.py](../../jiuwenswarm/server/live_voice/p3_production_intent_composition.py) | Voice 专有边界 | 882 |
| [jiuwenswarm/server/live_voice/presentation_ledger.py](../../jiuwenswarm/server/live_voice/presentation_ledger.py) | Voice 专有边界 | 1,272 |
| [jiuwenswarm/server/live_voice/product_authority.py](../../jiuwenswarm/server/live_voice/product_authority.py) | Voice 专有边界 | 1,302 |
| [jiuwenswarm/server/live_voice/product_composition_contract.py](../../jiuwenswarm/server/live_voice/product_composition_contract.py) | Voice 专有边界 | 424 |
| [jiuwenswarm/server/live_voice/product_composition_registry.py](../../jiuwenswarm/server/live_voice/product_composition_registry.py) | Voice 专有边界 | 15,093 |
| [jiuwenswarm/server/live_voice/product_composition_root.py](../../jiuwenswarm/server/live_voice/product_composition_root.py) | Voice 专有边界 | 459 |
| [jiuwenswarm/server/live_voice/product_diagnostic_projection.py](../../jiuwenswarm/server/live_voice/product_diagnostic_projection.py) | Voice 专有边界 | 596 |
| [jiuwenswarm/server/live_voice/product_observability_adapter.py](../../jiuwenswarm/server/live_voice/product_observability_adapter.py) | Voice 专有边界 | 847 |
| [jiuwenswarm/server/live_voice/product_observability_runtime.py](../../jiuwenswarm/server/live_voice/product_observability_runtime.py) | Voice 专有边界 | 1,425 |
| [jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py](../../jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py) | Voice 专有边界 | 2,127 |
| [jiuwenswarm/server/live_voice/product_p3_text_adapter.py](../../jiuwenswarm/server/live_voice/product_p3_text_adapter.py) | Voice 专有边界 | 1,207 |
| [jiuwenswarm/server/live_voice/production_task_classifier.py](../../jiuwenswarm/server/live_voice/production_task_classifier.py) | Voice 专有边界 | 162 |
| [jiuwenswarm/server/live_voice/production_task_intent.py](../../jiuwenswarm/server/live_voice/production_task_intent.py) | Voice 专有边界 | 2,026 |
| [jiuwenswarm/server/live_voice/progress_notification_arbiter.py](../../jiuwenswarm/server/live_voice/progress_notification_arbiter.py) | Voice 专有边界 | 2,228 |
| [jiuwenswarm/server/live_voice/semantic_continuity.py](../../jiuwenswarm/server/live_voice/semantic_continuity.py) | Voice 专有边界 | 255 |
| [jiuwenswarm/server/live_voice/speculative_dialogue.py](../../jiuwenswarm/server/live_voice/speculative_dialogue.py) | Voice 专有边界 | 459 |
| [jiuwenswarm/server/live_voice/speech_http_diagnostics.py](../../jiuwenswarm/server/live_voice/speech_http_diagnostics.py) | Voice 专有边界 | 63 |
| [jiuwenswarm/server/live_voice/speech_ports.py](../../jiuwenswarm/server/live_voice/speech_ports.py) | Voice 专有边界 | 477 |
| [jiuwenswarm/server/live_voice/speech_socket_diagnostics.py](../../jiuwenswarm/server/live_voice/speech_socket_diagnostics.py) | Voice 专有边界 | 239 |
| [jiuwenswarm/server/live_voice/streaming_speech.py](../../jiuwenswarm/server/live_voice/streaming_speech.py) | Voice 专有边界 | 2,255 |
| [jiuwenswarm/server/live_voice/task_control_presentation.py](../../jiuwenswarm/server/live_voice/task_control_presentation.py) | Voice 专有边界 | 174 |
| [jiuwenswarm/server/live_voice/task_core.py](../../jiuwenswarm/server/live_voice/task_core.py) | Voice 专有边界 | 211 |
| [jiuwenswarm/server/live_voice/task_event_subscription.py](../../jiuwenswarm/server/live_voice/task_event_subscription.py) | Voice 专有边界 | 1,568 |
| [jiuwenswarm/server/live_voice/task_progress_return.py](../../jiuwenswarm/server/live_voice/task_progress_return.py) | Voice 专有边界 | 2,291 |
| [jiuwenswarm/server/live_voice/task_result_context.py](../../jiuwenswarm/server/live_voice/task_result_context.py) | Voice 专有边界 | 531 |
| [jiuwenswarm/server/live_voice/task_semantics.py](../../jiuwenswarm/server/live_voice/task_semantics.py) | Voice 专有边界 | 1,210 |
| [jiuwenswarm/server/live_voice/unified_committed_input.py](../../jiuwenswarm/server/live_voice/unified_committed_input.py) | Voice 专有边界 | 1,694 |
| [jiuwenswarm/server/live_voice/voice_task_bridge.py](../../jiuwenswarm/server/live_voice/voice_task_bridge.py) | Voice 专有边界 | 197 |
| [jiuwenswarm/server/live_voice/voice_task_policy.py](../../jiuwenswarm/server/live_voice/voice_task_policy.py) | Voice 专有边界 | 739 |
| [jiuwenswarm/server/runtime/agent_adapter/background_task_checkpoint.py](../../jiuwenswarm/server/runtime/agent_adapter/background_task_checkpoint.py) | Voice 专有边界 | 181 |
| [jiuwenswarm/server/runtime/agent_adapter/formal_live_voice.py](../../jiuwenswarm/server/runtime/agent_adapter/formal_live_voice.py) | Voice 专有边界 | 480 |
| [jiuwenswarm/server/runtime/agent_adapter/formal_model_diagnostics.py](../../jiuwenswarm/server/runtime/agent_adapter/formal_model_diagnostics.py) | Voice 专有边界 | 320 |
| [jiuwenswarm/server/runtime/durability/durability_authority.py](../../jiuwenswarm/server/runtime/durability/durability_authority.py) | Host 通用服务 | 229 |
| [jiuwenswarm/server/runtime/durability/durability_checkpoint.py](../../jiuwenswarm/server/runtime/durability/durability_checkpoint.py) | Host 通用服务 | 499 |
| [jiuwenswarm/server/runtime/durability/durability_effects.py](../../jiuwenswarm/server/runtime/durability/durability_effects.py) | Host 通用服务 | 920 |
| [jiuwenswarm/server/runtime/durability/durability_identity.py](../../jiuwenswarm/server/runtime/durability/durability_identity.py) | Host 通用服务 | 150 |
| [jiuwenswarm/server/runtime/durability/durability_readers.py](../../jiuwenswarm/server/runtime/durability/durability_readers.py) | Host 通用服务 | 689 |
| [jiuwenswarm/server/runtime/durability/durability_recovery_facts.py](../../jiuwenswarm/server/runtime/durability/durability_recovery_facts.py) | Host 通用服务 | 466 |
| [jiuwenswarm/server/runtime/formal_tasks/executor_capabilities.py](../../jiuwenswarm/server/runtime/formal_tasks/executor_capabilities.py) | Host 通用服务 | 373 |
| [jiuwenswarm/server/runtime/formal_tasks/file_effect_plan.py](../../jiuwenswarm/server/runtime/formal_tasks/file_effect_plan.py) | Host 通用服务 | 416 |
| [jiuwenswarm/server/runtime/formal_tasks/formal_task_models.py](../../jiuwenswarm/server/runtime/formal_tasks/formal_task_models.py) | Host 通用服务 | 2,648 |
| [jiuwenswarm/server/runtime/formal_tasks/persistent_task_core.py](../../jiuwenswarm/server/runtime/formal_tasks/persistent_task_core.py) | Host 通用服务 | 1,645 |
| [jiuwenswarm/server/runtime/formal_tasks/project_code_executor.py](../../jiuwenswarm/server/runtime/formal_tasks/project_code_executor.py) | Host 通用服务 | 6,599 |
| [jiuwenswarm/server/runtime/formal_tasks/task_adjustment_queue.py](../../jiuwenswarm/server/runtime/formal_tasks/task_adjustment_queue.py) | Host 通用服务 | 352 |
| [jiuwenswarm/server/runtime/formal_tasks/task_store.py](../../jiuwenswarm/server/runtime/formal_tasks/task_store.py) | Host 通用服务 | 15,224 |
| [tests/support/live_voice/alpha_benchmark.py](../../tests/support/live_voice/alpha_benchmark.py) | 测试支撑 | 633 |
| [tests/support/live_voice/alpha_privacy_conformance.py](../../tests/support/live_voice/alpha_privacy_conformance.py) | 测试支撑 | 1,025 |
| [tests/support/live_voice/executor_port.py](../../tests/support/live_voice/executor_port.py) | 测试支撑 | 117 |
| [tests/support/live_voice/fake_verticals.py](../../tests/support/live_voice/fake_verticals.py) | 测试支撑 | 404 |
| [tests/support/live_voice/legacy_project_executor.py](../../tests/support/live_voice/legacy_project_executor.py) | 测试支撑 | 527 |
| [tests/support/live_voice/legacy_task_core.py](../../tests/support/live_voice/legacy_task_core.py) | 测试支撑 | 527 |
| [tests/support/live_voice/observability_fault_harness.py](../../tests/support/live_voice/observability_fault_harness.py) | 测试支撑 | 391 |
| [tests/support/live_voice/product_p2_readiness.py](../../tests/support/live_voice/product_p2_readiness.py) | 测试支撑 | 262 |
| [tests/support/live_voice/realtime_media.py](../../tests/support/live_voice/realtime_media.py) | 测试支撑 | 822 |
| [tests/support/live_voice/scripted_cascade.py](../../tests/support/live_voice/scripted_cascade.py) | 测试支撑 | 276 |
| [tests/support/live_voice/sli_window_contract.py](../../tests/support/live_voice/sli_window_contract.py) | 测试支撑 | 386 |
| [tests/support/live_voice/telemetry_privacy_contract.py](../../tests/support/live_voice/telemetry_privacy_contract.py) | 测试支撑 | 221 |
