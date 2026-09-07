# LiveVoice 设计简化：逐文件 symbol 清单（自动生成）

> 由 `scripts/live_voice/slimming/symbol_inventory.py --rev HEAD` 生成；口径见脚本 docstring。
> `callers` 是导入该模块并提及该 symbol 的**其他生产文件**数；`文件内引用` 是定义之外在本文件内的提及次数（工厂、同文件使用）。两者都为 0 才是静态无引用，删除前仍需 grep 复核。
> 每个文件按 symbol 行数降序，最多列前 40 个。

## 01 Browser Audio Edge（6 文件，9,023 行）

### `channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`（4,408 行；被 1 个生产文件导入；22 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `parseProductP1NativeChatProjection` | function | 52 | 0 | 1 |  |
| `parseProductP1NativeInteractionActivation` | function | 18 | 0 | 1 |  |
| `ProductP1CaptureDiagnostics` | type | 17 | 0 | 1 |  |
| `productCaptureTerminalFailureReason` | function | 13 | 0 | 1 |  |
| `ProductP1CaptureProcessingDiagnostics` | type | 8 | 0 | 2 |  |
| `ProductP1CaptureRotationDiagnostics` | type | 7 | 0 | 3 |  |
| `ProductP1NativeChatMessage` | type | 6 | 0 | 8 |  |
| `ProductP1AudioDeviceSelection` | type | 5 | 0 | 3 |  |
| `NativeInteractionActivation` | type | 5 | 0 | 2 |  |
| `ProductP1NativeAudioInput` | type | 5 | 0 | 2 |  |
| `ProductP1Recognition` | type | 4 | 0 | 3 |  |
| `PRODUCT_P1_MEDIA_ACTIVATE_METHOD` | const | 1 | 0 | 2 |  |
| `PRODUCT_P1_MEDIA_CLOSE_METHOD` | const | 1 | 0 | 1 |  |
| `PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD` | const | 1 | 0 | 1 |  |
| `PRODUCT_P1_CAPTURE_MAX_DURATION_MS` | const | 1 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON` | const | 1 | 1 | 3 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_P1_EMPTY_TRANSCRIPT_REASON` | const | 1 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_P1_PLAYOUT_QUEUE_CAPACITY` | const | 1 | 0 | 4 |  |
| `PRODUCT_P1_STREAMING_PLAYOUT_MAX_DURATION_MS` | const | 1 | 0 | 1 |  |
| `ProductP1VoiceStatus` | type | 1 | 1 | 6 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductP1InteractionEngine` | type | 1 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductP1VoiceRouteOwner` | class | 1 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |

### `channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts`（3,088 行；被 8 个生产文件导入；53 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `inspectBrowserAudioPlatform` | function | 29 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/webPlatformDiagnostics.ts |
| `BrowserAudioCaptureMetadata` | type | 27 | 0 | 3 |  |
| `BrowserAudioLocalStopReceipt` | type | 24 | 1 | 2 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `BrowserAudioContextLike` | type | 15 | 0 | 15 |  |
| `BrowserAudioPlatformCapability` | type | 15 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/webPlatformDiagnostics.ts |
| `BrowserAudioEnvironment` | type | 12 | 1 | 6 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `BrowserAudioPlayoutScheduledEvent` | type | 11 | 1 | 2 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `BrowserAudioTentativePauseOutcome` | type | 11 | 0 | 2 |  |
| `BrowserAudioTrackLike` | type | 10 | 0 | 4 |  |
| `BrowserAudioIOViolation` | class | 10 | 0 | 103 |  |
| `BrowserAudioIOAdapterOptions` | type | 10 | 0 | 1 |  |
| `BrowserAudioLocalStopOutcome` | type | 9 | 0 | 2 |  |
| `BrowserAudioPcmChunk` | type | 9 | 2 | 1 | channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts, channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `BrowserAudioTrackSettingsLike` | type | 8 | 0 | 1 |  |
| `BrowserAudioObserver` | type | 8 | 1 | 2 | channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts |
| `BrowserAudioTentativePauseReceipt` | type | 8 | 0 | 3 |  |
| `BrowserAudioPlayoutMetadata` | type | 7 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `BrowserAudioPlayoutEvent` | type | 7 | 2 | 1 | channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts, channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `BrowserMediaDevicesLike` | type | 6 | 0 | 3 |  |
| `BrowserAudioGainNodeLike` | type | 6 | 0 | 2 |  |
| `BrowserAudioBufferSourceLike` | type | 6 | 0 | 3 |  |
| `BrowserAudioSourceActionConfirmation` | type | 6 | 0 | 3 |  |
| `BrowserAudioCaptureStateEvent` | type | 6 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts |
| `BrowserAudioDocumentLike` | type | 5 | 0 | 2 |  |
| `BrowserMediaDeviceInfoLike` | type | 5 | 0 | 1 |  |
| `BrowserPermissionStatusLike` | type | 5 | 0 | 7 |  |
| `BrowserAudioPlayoutDrainReceipt` | type | 5 | 0 | 5 |  |
| `BrowserMediaStreamLike` | type | 4 | 1 | 8 | channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts |
| `BrowserAudioMessagePortLike` | type | 4 | 0 | 1 |  |
| `BrowserAudioNodeLike` | type | 4 | 0 | 8 |  |
| `BrowserAudioWorkletNodeLike` | type | 4 | 0 | 6 |  |
| `BrowserAudioConfirmedCursor` | type | 4 | 0 | 4 |  |
| `BrowserAudioDeviceEvent` | type | 4 | 1 | 2 | channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts |
| `BrowserAudioCaptureStreamFactory` | type | 3 | 4 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx, channels/web/frontend/src/components/ChatPanel/index.tsx, channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts |
| `BrowserPermissionsLike` | type | 3 | 0 | 3 |  |
| `BrowserAudioBufferLike` | type | 3 | 0 | 5 |  |
| `BrowserAudioPlayoutDrain` | type | 3 | 1 | 4 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `BrowserAudioCaptureState` | type | 1 | 0 | 4 |  |
| `BrowserAudioPlayoutState` | type | 1 | 0 | 4 |  |
| `BrowserAudioSourceActionStatus` | type | 1 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/formal/browserAudioDeviceSelection.ts`（534 行；被 1 个生产文件导入；14 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `BrowserAudioDeviceSelectionOwner` | class | 385 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `BrowserAudioDeviceSelectionSnapshot` | type | 10 | 1 | 6 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `BrowserAudioDeviceSelectionStatus` | type | 9 | 0 | 2 |  |
| `BrowserAudioSelectionMediaDevicesLike` | type | 6 | 0 | 2 |  |
| `BrowserAudioDeviceSelectionEnvironment` | type | 6 | 0 | 4 |  |
| `BrowserAudioDeviceSelectionViolation` | class | 6 | 0 | 22 |  |
| `BrowserAudioSelectionDeviceLike` | type | 5 | 0 | 2 |  |
| `BrowserAudioSelectionPermissionLike` | type | 5 | 0 | 5 |  |
| `BrowserAudioDeviceOption` | type | 5 | 0 | 3 |  |
| `BrowserAudioAppliedDeviceRoute` | type | 5 | 0 | 1 |  |
| `BrowserAudioSelectionTrackLike` | type | 3 | 0 | 2 |  |
| `BrowserAudioSelectionStreamLike` | type | 3 | 0 | 2 |  |
| `BrowserAudioDeviceSelectionKind` | type | 1 | 0 | 2 |  |
| `BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN` | const | 1 | 1 | 11 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |

### `channels/web/frontend/src/features/live-voice/formal/browserLiveVoiceOwnership.ts`（426 行；被 1 个生产文件导入；8 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `BrowserLiveVoiceOwnership` | type | 7 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts |
| `BrowserLiveVoiceOwnershipEnvironment` | type | 6 | 0 | 2 |  |
| `BrowserLiveVoiceOwnershipBarrier` | type | 4 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts |
| `createBrowserLiveVoiceOwnershipBarrier` | function | 3 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts |
| `createBrowserLiveVoiceOwnership` | function | 2 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts |
| `BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE` | const | 1 | 0 | 10 |  |
| `BROWSER_LIVE_VOICE_OWNERSHIP_SUPERSEDED` | const | 1 | 0 | 5 |  |
| `BROWSER_LIVE_VOICE_TAKEOVER_CLEANUP_PENDING` | const | 1 | 0 | 3 |  |

### `channels/web/frontend/src/features/live-voice/formal/audioPort.ts`（364 行；被 6 个生产文件导入；17 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `AudioPort` | class | 148 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts |
| `createCapturedAudioFrame` | function | 46 | 3 | 0 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts, channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts, channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts |
| `createAudioRenderPlan` | function | 23 | 2 | 0 | channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts, channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `NearEndSpeechCandidate` | type | 15 | 2 | 0 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts, channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `audioFrameSamples` | function | 10 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts |
| `AudioPortViolation` | class | 9 | 1 | 25 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts |
| `CapturedAudioFrame` | type | 8 | 4 | 2 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts, channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts, channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts |
| `AudioChunk` | type | 7 | 0 | 3 |  |
| `AudioFrameFormat` | type | 7 | 0 | 1 |  |
| `AudioRenderTransform` | type | 6 | 0 | 2 |  |
| `AudioResponseRef` | type | 5 | 4 | 14 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts, channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechSynthesisAdapter.ts, channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts |
| `AudioProviderRef` | type | 5 | 4 | 1 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts, channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechRecognitionAdapter.ts, channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechSynthesisAdapter.ts |
| `AudioFrozenPrefix` | type | 5 | 1 | 4 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts |
| `AudioCaptureRef` | type | 5 | 0 | 2 |  |
| `AudioRenderPlan` | type | 5 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts |
| `AudioAcceptedCursor` | type | 4 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts |
| `LIVE_VOICE_AUDIO_FRAME_DURATION_MS` | const | 1 | 3 | 4 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts, channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts, channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |

### `channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js`（203 行；被 0 个生产文件导入；0 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|

## 02 Web/Gateway media transport（10 文件，19,239 行）

### `gateway/live_voice/dedicated_media_registration.py`（8,427 行；被 2 个生产文件导入；86 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `DedicatedMediaProductRegistry` | owner | 6726 | 1 | 6 | gateway/channel_manager/web/app_web_handlers.py |
| `handle_registered_media_socket` | function | 206 | 1 | 1 | gateway/channel_manager/web/web_connect.py |
| `register_dedicated_media_rpc_handlers` | function | 183 | 1 | 1 | gateway/channel_manager/web/app_web_handlers.py |
| `_StreamingSynthesisDiagnosticOwner` | owner | 104 | 0 | 3 |  |
| `_MediaAuthority` | value | 91 | 0 | 51 |  |
| `_StreamingObservabilityOwner` | owner | 84 | 0 | 1 |  |
| `_StreamingSynthesisDiagnosticWorker` | class | 55 | 0 | 1 |  |
| `_NativeMediaSession` | value | 52 | 0 | 32 |  |
| `_MediaFirstFrameDiagnosticWorker` | class | 50 | 0 | 1 |  |
| `_downlink_frames` | function | 49 | 0 | 1 |  |
| `_parse_media_auth_frame` | function | 47 | 0 | 1 |  |
| `_native_downlink_frames` | function | 42 | 0 | 1 |  |
| `_synthesis_authorization_binding` | function | 42 | 0 | 5 |  |
| `_has_formal_p2_manifest` | function | 40 | 0 | 2 |  |
| `_authenticate_registered_media_socket` | function | 37 | 0 | 1 |  |
| `_resample_native_frame` | function | 26 | 0 | 2 |  |
| `_ProductActivationAuthority` | value | 22 | 0 | 4 |  |
| `_l0_media_binding` | function | 21 | 0 | 8 |  |
| `_terminal_preparation_event_key` | function | 21 | 0 | 1 |  |
| `_P2_NOTIFICATION_ITEM_KEYS` | constant | 20 | 0 | 1 |  |
| `_streaming_error_envelope` | function | 18 | 0 | 7 |  |
| `_required_id` | function | 17 | 0 | 106 |  |
| `_wav_bytes` | function | 17 | 0 | 2 |  |
| `_PLAYOUT_RECEIPT_REQUEST_FIELDS` | constant | 16 | 0 | 2 |  |
| `_native_audio_extends_batch` | function | 13 | 0 | 1 |  |
| `_NativeNotificationSequenceFence` | value | 13 | 0 | 3 |  |
| `_P2_NOTIFICATION_BATCH_KEYS` | constant | 11 | 0 | 1 |  |
| `_SynthesisAuthorityTransfer` | value | 11 | 0 | 7 |  |
| `_MediaFirstFrameDiagnosticItem` | value | 9 | 0 | 3 |  |
| `_FORMAL_P2_EVIDENCE` | constant | 8 | 0 | 1 |  |
| `_request_origin` | function | 7 | 0 | 8 |  |
| `_pcm16` | function | 7 | 0 | 2 |  |
| `_safe_uint` | function | 6 | 0 | 34 |  |
| `_binding_payload` | function | 5 | 0 | 5 |  |
| `_StreamingObservationContext` | value | 5 | 0 | 7 |  |
| `_js_round` | function | 4 | 0 | 1 |  |
| `_StreamingDiagnosticItem` | value | 4 | 0 | 3 |  |
| `_NATIVE_PROVIDER_TRANSPORT_FAILURES` | constant | 3 | 0 | 2 |  |
| `_NATIVE_ORDERED_CONTROL_OPERATIONS` | constant | 3 | 0 | 1 |  |
| `StreamingXObsMetric` | constant | 3 | 0 | 4 |  |

### `gateway/live_voice/streaming_synthesis_route.py`（2,449 行；被 3 个生产文件导入；44 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `StreamingSynthesisRouteOwner` | owner | 1634 | 3 | 1 | gateway/channel_manager/web/app_web_handlers.py, gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/product_streaming_synthesis.py |
| `_BoundedHardDeadlineOwner` | owner | 151 | 0 | 3 |  |
| `_request_binding_ref_inner` | function | 94 | 0 | 1 |  |
| `StreamingSynthesisRouteFact` | value | 45 | 0 | 3 |  |
| `StreamingSynthesisHandle` | value | 42 | 1 | 27 | gateway/live_voice/product_streaming_synthesis.py |
| `StreamingSynthesisChunk` | value | 37 | 1 | 4 | gateway/live_voice/product_streaming_synthesis.py |
| `_reason_for_exception` | function | 31 | 0 | 3 |  |
| `_capability_provenance` | function | 30 | 0 | 1 |  |
| `_prepare_synthesis_request` | function | 27 | 0 | 1 |  |
| `StreamingSynthesisCapabilityProvenance` | value | 25 | 0 | 7 |  |
| `_TaskReservation` | value | 17 | 0 | 4 |  |
| `_synthesis_scope_identity` | function | 15 | 0 | 1 |  |
| `StreamingSynthesisReason` | value | 14 | 1 | 54 | gateway/live_voice/product_streaming_synthesis.py |
| `StreamingSynthesisOutcome` | value | 11 | 2 | 13 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/product_streaming_synthesis.py |
| `_fresh_process_control` | function | 11 | 0 | 1 |  |
| `_capture_process_control` | function | 10 | 0 | 1 |  |
| `StreamingSynthesisPull` | value | 10 | 0 | 11 |  |
| `_PreparedSynthesisRequest` | value | 9 | 0 | 4 |  |
| `_safe_provider_id` | function | 9 | 0 | 4 |  |
| `_bounded_timeout` | function | 9 | 0 | 5 |  |
| `_decode_pcm_s16le` | function | 7 | 0 | 1 |  |
| `StreamingSynthesisRouteViolation` | exception | 6 | 1 | 47 | gateway/live_voice/dedicated_media_registration.py |
| `_drain_queue` | function | 6 | 0 | 6 |  |
| `_LEGACY_SYNTHESIS_SCOPE` | constant | 5 | 0 | 3 |  |
| `_discard_awaitable` | function | 5 | 0 | 3 |  |
| `StreamingSynthesisFallbackAction` | value | 4 | 0 | 7 |  |
| `_scoped_stream_key` | function | 4 | 0 | 2 |  |
| `_bounded_positive_int` | function | 4 | 0 | 3 |  |
| `_ExternalResult` | value | 3 | 0 | 6 |  |
| `_CloseResult` | value | 3 | 0 | 3 |  |
| `_TerminalSignal` | value | 2 | 0 | 7 |  |
| `_LOGGER` | constant | 1 | 1 | 5 | gateway/live_voice/dedicated_media_registration.py |
| `_DEFAULT_MAX_ACTIVE_STREAMS` | constant | 1 | 0 | 2 |  |
| `_DEFAULT_MAX_PENDING_FRAMES` | constant | 1 | 0 | 2 |  |
| `_DEFAULT_OPEN_TIMEOUT_SECONDS` | constant | 1 | 0 | 1 |  |
| `_DEFAULT_EVENT_TIMEOUT_SECONDS` | constant | 1 | 0 | 1 |  |
| `_DEFAULT_QUEUE_WAIT_SECONDS` | constant | 1 | 0 | 1 |  |
| `_PROVIDER_CLEANUP_TIMEOUT_SECONDS` | constant | 1 | 0 | 9 |  |
| `_DEFAULT_MAX_RETAINED_TASKS` | constant | 1 | 0 | 2 |  |
| `_CLEANUP_TASK_RESERVE` | constant | 1 | 0 | 2 |  |

### `gateway/live_voice/dedicated_media_route.py`（1,869 行；被 4 个生产文件导入；31 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `run_dedicated_media_socket_leaf` | function | 594 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `run_dedicated_media_downlink_socket_leaf` | function | 549 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `DedicatedMediaLeafCleanupOwner` | owner | 118 | 1 | 6 | gateway/live_voice/dedicated_media_registration.py |
| `_DedicatedMediaRouteSession` | owner | 109 | 0 | 3 |  |
| `DedicatedMediaSocketLeafResult` | value | 78 | 1 | 16 | gateway/live_voice/dedicated_media_registration.py |
| `DedicatedMediaRouteEvidence` | value | 47 | 0 | 8 |  |
| `create_dedicated_media_route` | function | 43 | 0 | 2 |  |
| `_canonical_origin` | function | 40 | 0 | 2 |  |
| `InactiveDedicatedMediaRoute` | value | 29 | 0 | 5 |  |
| `ActiveDedicatedMediaRoute` | value | 21 | 0 | 3 |  |
| `_inactive` | function | 15 | 0 | 6 |  |
| `DedicatedMediaRouteRequest` | value | 9 | 1 | 6 | gateway/live_voice/dedicated_media_registration.py |
| `DedicatedMediaRouteSnapshot` | value | 9 | 0 | 3 |  |
| `DedicatedMediaDownlinkSourceFailure` | exception | 8 | 3 | 3 | gateway/live_voice/native_response_downlink.py, gateway/live_voice/product_streaming_synthesis.py, gateway/live_voice/task_notification_preparation.py |
| `DedicatedMediaRouteReason` | value | 8 | 0 | 25 |  |
| `_canonical_evidence` | function | 8 | 0 | 3 |  |
| `DedicatedMediaSocket` | value | 8 | 0 | 3 |  |
| `_await_owned_call` | function | 6 | 0 | 6 |  |
| `DedicatedMediaLeafCleanupSnapshot` | value | 6 | 1 | 3 | gateway/live_voice/dedicated_media_registration.py |
| `DedicatedMediaRouteTruth` | value | 3 | 0 | 12 |  |
| `DedicatedMediaRouteActivation` | constant | 3 | 0 | 2 |  |
| `_is_same_origin` | function | 3 | 0 | 2 |  |
| `DEDICATED_MEDIA_ROUTE_CONTRACT_VERSION` | constant | 1 | 0 | 2 |  |
| `MEDIA_ROUTE_REGISTRATION_UNAVAILABLE` | constant | 1 | 0 | 3 |  |
| `MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN` | constant | 1 | 0 | 4 |  |
| `_DOMAIN_LABEL` | constant | 1 | 0 | 1 |  |
| `_ROUTE_CONSTRUCTION_TOKEN` | constant | 1 | 0 | 2 |  |
| `_SOCKET_CLOSE_TIMEOUT_SECONDS` | constant | 1 | 0 | 6 |  |
| `_MAX_PENDING_FRAMES` | constant | 1 | 0 | 1 |  |
| `_MAX_PENDING_BYTES` | constant | 1 | 0 | 1 |  |
| `_PROCESS_CONTROL` | constant | 1 | 0 | 5 |  |

### `channels/web/frontend/src/features/live-voice/formal/adapters/browserGatewayMediaTransport.ts`（1,642 行；被 2 个生产文件导入；47 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `BrowserGatewayMediaRegistrationOwner` | class | 225 | 0 | 2 |  |
| `deserializeMediaControl` | function | 179 | 2 | 0 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts, channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `BoundedMediaSender` | class | 162 | 0 | 2 |  |
| `StrictMediaReceiver` | class | 115 | 0 | 2 |  |
| `serializeMediaControl` | function | 73 | 2 | 0 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts, channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `decodeAudioFrame` | function | 59 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `createBrowserGatewayMediaActivation` | function | 51 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `MediaLeafLifecycleFact` | type | 37 | 0 | 6 |  |
| `encodeAudioFrame` | function | 37 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `validatePlaybackStopReceipt` | function | 28 | 0 | 1 |  |
| `MediaDetachReason` | type | 27 | 1 | 12 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `createPlaybackStopReceipt` | function | 24 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `boundedMediaConsumerFailureReason` | function | 21 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `MediaAuthorityBinding` | type | 15 | 1 | 21 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `MediaEndOfTurn` | type | 15 | 2 | 1 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts, channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `MediaCapability` | type | 15 | 0 | 3 |  |
| `MediaSpeechStart` | type | 13 | 2 | 1 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts, channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `MediaActivationRequest` | type | 11 | 0 | 1 |  |
| `MediaPlaybackStopReceipt` | type | 10 | 1 | 5 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `MediaLeafLifecycleEvent` | type | 10 | 0 | 3 |  |
| `MediaPlaybackStopOutcome` | type | 9 | 0 | 4 |  |
| `MediaTransportViolation` | class | 9 | 1 | 63 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `InactiveMediaActivation` | type | 9 | 0 | 3 |  |
| `MediaRegistrationOwnerCloseResult` | type | 9 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `MediaFrameFormat` | type | 8 | 0 | 2 |  |
| `MediaDetach` | type | 8 | 1 | 18 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `MediaCloseResult` | type | 8 | 0 | 3 |  |
| `MediaAck` | type | 6 | 1 | 5 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `ActiveMediaActivation` | type | 6 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `MediaDrainResult` | type | 6 | 0 | 2 |  |
| `MediaGenerationBinding` | type | 5 | 0 | 1 |  |
| `MediaPlayoutBinding` | type | 5 | 0 | 2 |  |
| `MediaAudioFrame` | type | 5 | 2 | 9 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts, channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `MediaConsumerFailureFallback` | type | 5 | 0 | 1 |  |
| `MediaAttach` | type | 4 | 0 | 3 |  |
| `MediaEnqueueResult` | type | 4 | 1 | 2 | channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `MEDIA_CONTRACT_VERSION` | const | 1 | 0 | 4 |  |
| `MEDIA_TRANSPORT_KIND` | const | 1 | 0 | 2 |  |
| `MEDIA_WIRE_CODEC` | const | 1 | 0 | 2 |  |
| `MEDIA_CAPTURE_ENCODING` | const | 1 | 0 | 5 |  |

### `channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts`（1,442 行；被 1 个生产文件导入；19 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `BrowserDedicatedMediaSocketLeaf` | class | 800 | 0 | 2 |  |
| `createBrowserDedicatedMediaRoute` | function | 137 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `BrowserDedicatedMediaRouteRequest` | type | 29 | 0 | 1 |  |
| `DedicatedMediaSocketLike` | type | 12 | 0 | 4 |  |
| `MediaFirstFrameDiagnostic` | type | 10 | 1 | 7 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `DedicatedMediaRouteCapability` | type | 10 | 0 | 3 |  |
| `InactiveBrowserDedicatedMediaRoute` | type | 10 | 0 | 3 |  |
| `DedicatedMediaTerminalEvent` | type | 7 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `ActiveBrowserDedicatedMediaRoute` | type | 6 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `DedicatedMediaSocketMessageEventLike` | type | 3 | 0 | 1 |  |
| `DEDICATED_MEDIA_SUBPROTOCOL` | const | 1 | 0 | 2 |  |
| `DEDICATED_MEDIA_ROUTE_PATH` | const | 1 | 0 | 1 |  |
| `DEDICATED_MEDIA_AUTH_CONTRACT_VERSION` | const | 1 | 0 | 1 |  |
| `DEDICATED_MEDIA_ROUTE_EVIDENCE_SCOPE` | const | 1 | 0 | 2 |  |
| `DedicatedMediaSocketFactory` | type | 1 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `DedicatedMediaDrainRetryScheduler` | type | 1 | 0 | 4 |  |
| `DedicatedMediaDrainRetryCanceller` | type | 1 | 0 | 4 |  |
| `DedicatedMediaTerminalSource` | type | 1 | 0 | 4 |  |
| `BrowserDedicatedMediaRouteActivation` | type | 1 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |

### `gateway/live_voice/browser_gateway_media_transport.py`（1,437 行；被 7 个生产文件导入；67 个顶层 symbol，其中 2 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `deserialize_media_control` | function | 184 | 2 | 0 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py |
| `BoundedMediaSender` | class | 163 | 1 | 2 | gateway/live_voice/dedicated_media_route.py |
| `StrictMediaReceiver` | class | 107 | 1 | 2 | gateway/live_voice/dedicated_media_route.py |
| `_parse_binding` | function | 93 | 0 | 1 |  |
| `decode_audio_frame` | function | 71 | 0 | 1 |  |
| `MediaAuthorityBinding` | value | 63 | 3 | 14 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py, gateway/live_voice/streaming_speech_route.py |
| `serialize_media_control` | function | 48 | 2 | 0 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py |
| `encode_audio_frame` | function | 45 | 0 | 1 |  |
| `MediaFrameFormat` | value | 43 | 1 | 2 | gateway/live_voice/dedicated_media_registration.py |
| `MediaEndOfTurn` | value | 40 | 2 | 3 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py |
| `create_gateway_media_activation` | function | 37 | 0 | 0 |  |
| `MediaSpeechStart` | value | 32 | 2 | 3 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py |
| `validate_playback_stop_receipt` | function | 30 | 2 | 1 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py |
| `MediaDetachReason` | value | 27 | 5 | 16 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py, gateway/live_voice/native_response_downlink.py |
| `create_playback_stop_receipt` | function | 27 | 0 | 0 |  |
| `MediaPlaybackStopReceipt` | value | 25 | 2 | 7 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py |
| `MediaDetach` | value | 21 | 1 | 14 | gateway/live_voice/dedicated_media_route.py |
| `_capability` | function | 16 | 0 | 2 |  |
| `MediaCapability` | value | 14 | 0 | 4 |  |
| `MediaCloseResult` | value | 13 | 1 | 6 | gateway/live_voice/dedicated_media_route.py |
| `MediaGenerationBinding` | value | 12 | 1 | 2 | gateway/live_voice/dedicated_media_registration.py |
| `_check_control_id` | function | 12 | 0 | 20 |  |
| `_coerce_detach_reason` | function | 11 | 0 | 2 |  |
| `_require_safe_uint` | function | 11 | 0 | 25 |  |
| `MediaAck` | value | 10 | 2 | 6 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py |
| `_control_to_dict` | function | 10 | 0 | 1 |  |
| `MediaPlaybackStopOutcome` | value | 9 | 1 | 7 | gateway/live_voice/dedicated_media_registration.py |
| `MediaPlayoutBinding` | value | 9 | 1 | 2 | gateway/live_voice/dedicated_media_registration.py |
| `MediaAttach` | value | 9 | 2 | 5 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py |
| `MediaControl` | constant | 8 | 0 | 3 |  |
| `MediaActivationRequest` | value | 7 | 0 | 1 |  |
| `_require_exact_keys` | function | 7 | 0 | 10 |  |
| `MediaTransportViolation` | exception | 6 | 3 | 67 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py, gateway/live_voice/native_response_downlink.py |
| `ActiveMediaActivation` | value | 6 | 0 | 2 |  |
| `_require_mapping` | function | 6 | 0 | 5 |  |
| `_require_zero_business_cancel` | function | 5 | 0 | 10 |  |
| `MediaDrainResult` | value | 5 | 0 | 3 |  |
| `_check_control_uint` | function | 5 | 0 | 6 |  |
| `_binding_to_dict` | function | 5 | 0 | 1 |  |
| `BinarySendDisposition` | value | 4 | 1 | 4 | gateway/live_voice/dedicated_media_route.py |

### `channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts`（1,431 行；被 1 个生产文件导入；31 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `GatewayBatchSpeechClient` | class | 819 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `capturedFramesToPcm16Wav` | function | 53 | 0 | 2 |  |
| `FormalSynthesisInput` | type | 18 | 0 | 2 |  |
| `LocalSpeechCapability` | type | 18 | 0 | 1 |  |
| `normalizeStreamingXObs` | function | 14 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `FormalBatchRecognitionResult` | type | 14 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `FormalSynthesisDownlink` | type | 14 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `FormalStreamingRecognitionResult` | type | 13 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `FormalRecognitionInput` | type | 13 | 0 | 2 |  |
| `FormalTaskPreparationInput` | type | 13 | 1 | 4 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `GatewaySpeechCapabilityEvidence` | type | 12 | 0 | 1 |  |
| `GatewayBatchSpeechError` | class | 12 | 0 | 55 |  |
| `STREAMING_SPEECH_DEGRADATION_REASONS` | const | 10 | 0 | 2 |  |
| `FormalStreamingRecognitionFallback` | type | 9 | 0 | 1 |  |
| `FormalBatchSynthesisResult` | type | 9 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `GatewaySpeechScope` | type | 6 | 0 | 2 |  |
| `GatewaySpeechProvider` | type | 6 | 1 | 4 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `GatewaySpeechTransport` | type | 4 | 0 | 2 |  |
| `isStreamingSpeechDegradationReason` | function | 3 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `FormalStreamingRecognitionDecision` | type | 2 | 0 | 1 |  |
| `LIVE_VOICE_SPEECH_CONTRACT_VERSION` | const | 1 | 0 | 7 |  |
| `SPEECH_CAPABILITIES_METHOD` | const | 1 | 0 | 1 |  |
| `SPEECH_RECOGNIZE_BATCH_METHOD` | const | 1 | 0 | 1 |  |
| `SPEECH_RECOGNIZE_STREAMING_RESULT_METHOD` | const | 1 | 0 | 1 |  |
| `SPEECH_SYNTHESIZE_BATCH_METHOD` | const | 1 | 0 | 1 |  |
| `SPEECH_CANCEL_METHOD` | const | 1 | 0 | 1 |  |
| `StreamingSpeechDegradationReason` | type | 1 | 0 | 2 |  |
| `StreamingXObsEvent` | type | 1 | 0 | 2 |  |
| `StreamingXObsMetric` | type | 1 | 0 | 2 |  |
| `GatewaySpeechOperation` | type | 1 | 0 | 1 |  |
| `TASK_PREPARATION_VERSION` | const | 1 | 0 | 5 |  |

### `gateway/live_voice/task_notification_preparation.py`（327 行；被 1 个生产文件导入；15 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `PreparedNotificationSource` | value | 130 | 1 | 10 | gateway/live_voice/dedicated_media_registration.py |
| `TaskNotificationPreparationOwner` | owner | 126 | 1 | 0 | gateway/live_voice/dedicated_media_registration.py |
| `PreparationIdentity` | value | 20 | 1 | 5 | gateway/live_voice/dedicated_media_registration.py |
| `PreparationViolation` | exception | 4 | 1 | 14 | gateway/live_voice/dedicated_media_registration.py |
| `CONTRACT_VERSION` | constant | 1 | 1 | 0 | gateway/live_voice/dedicated_media_registration.py |
| `CAPABILITIES_METHOD` | constant | 1 | 1 | 0 | gateway/live_voice/dedicated_media_registration.py |
| `PREPARE_METHOD` | constant | 1 | 1 | 0 | gateway/live_voice/dedicated_media_registration.py |
| `CLAIM_METHOD` | constant | 1 | 1 | 0 | gateway/live_voice/dedicated_media_registration.py |
| `CANCEL_METHOD` | constant | 1 | 1 | 0 | gateway/live_voice/dedicated_media_registration.py |
| `MAX_FRAMES` | constant | 1 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `MAX_BYTES` | constant | 1 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `RETENTION_SECONDS` | constant | 1 | 1 | 2 | gateway/live_voice/dedicated_media_registration.py |
| `PRODUCTION_SECONDS` | constant | 1 | 0 | 1 |  |
| `RENDER_SECONDS` | constant | 1 | 0 | 2 |  |
| `MAX_SLOTS` | constant | 1 | 0 | 1 |  |

### `gateway/live_voice/product_streaming_synthesis.py`（212 行；被 1 个生产文件导入；4 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductStreamingSynthesisSource` | value | 116 | 1 | 4 | gateway/live_voice/dedicated_media_registration.py |
| `start_product_streaming_synthesis` | function | 36 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `ProductStreamingSynthesisStart` | value | 7 | 0 | 5 |  |
| `OutcomeObserver` | constant | 1 | 0 | 3 |  |

### `gateway/live_voice/__init__.py`（3 行；被 0 个生产文件导入；0 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|

## 03 Speech provider（5 文件，9,909 行）

### `server/live_voice/openai_streaming_speech.py`（2,921 行；被 4 个生产文件导入；85 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `OpenAIStreamingSpeechProvider` | class | 1489 | 0 | 5 |  |
| `_TransportCleanupOwner` | owner | 251 | 0 | 1 |  |
| `_DegradationSinkTaskOwner` | owner | 113 | 0 | 2 |  |
| `_StreamingLinearResampler` | class | 68 | 0 | 4 |  |
| `_validate_transcription_session` | function | 55 | 0 | 1 |  |
| `select_environment_streaming_speech` | function | 54 | 1 | 1 | gateway/channel_manager/web/app_web_handlers.py |
| `_reason_for_exception` | function | 38 | 2 | 4 | gateway/live_voice/streaming_speech_route.py, gateway/live_voice/streaming_synthesis_route.py |
| `_RecognitionSession` | value | 37 | 0 | 19 |  |
| `_default_sse_factory` | function | 37 | 0 | 1 |  |
| `SpeechDegradationFact` | value | 32 | 2 | 12 | gateway/live_voice/streaming_speech_route.py, gateway/live_voice/streaming_synthesis_route.py |
| `_turn_detection_echo_accepted` | function | 26 | 0 | 2 |  |
| `_safe_boundary_exception` | function | 25 | 0 | 17 |  |
| `_degradation_fact` | function | 23 | 0 | 3 |  |
| `OpenAIStreamingSpeechConfig` | value | 21 | 0 | 5 |  |
| `_json_object` | function | 20 | 0 | 2 |  |
| `_safe_transport_exception` | function | 17 | 0 | 4 |  |
| `_log_transport_cleanup` | function | 16 | 0 | 5 |  |
| `_provider_text` | function | 16 | 0 | 2 |  |
| `_await_cleanup` | function | 15 | 0 | 2 |  |
| `_same_cleanup` | function | 15 | 0 | 2 |  |
| `_turn_detection_value` | function | 15 | 0 | 2 |  |
| `_configuration_fallback` | function | 14 | 0 | 2 |  |
| `_safe_label` | function | 13 | 0 | 7 |  |
| `_HttpxSseStream` | class | 12 | 0 | 1 |  |
| `SpeechDegradationReason` | value | 11 | 0 | 15 |  |
| `_SynthesisSession` | value | 11 | 0 | 12 |  |
| `_await_sink` | function | 11 | 0 | 1 |  |
| `_await_cancelled_task` | function | 11 | 0 | 1 |  |
| `_realtime_url` | function | 11 | 0 | 1 |  |
| `_encode_s16le` | function | 11 | 0 | 4 |  |
| `_log_transport_cleanup_deferred` | function | 10 | 0 | 4 |  |
| `_settle_close_action` | function | 10 | 0 | 4 |  |
| `_required_secret` | function | 10 | 0 | 1 |  |
| `_provider_milliseconds` | function | 10 | 0 | 2 |  |
| `_first_process_control` | function | 9 | 0 | 3 |  |
| `TransportCleanupSnapshot` | value | 8 | 0 | 5 |  |
| `_discard_sink_awaitable` | function | 8 | 0 | 3 |  |
| `_log_sink_unavailable` | function | 8 | 0 | 8 |  |
| `_supported_sample_rate` | function | 7 | 0 | 2 |  |
| `_require_primary_audio_content` | function | 7 | 0 | 2 |  |

### `server/live_voice/batch_speech.py`（2,745 行；被 5 个生产文件导入；87 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `FormalBatchSpeechService` | owner | 1207 | 3 | 0 | gateway/channel_manager/web/app_web_handlers.py, gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/speech_rpc.py |
| `OpenAICompatibleBatchSpeechProvider` | class | 238 | 0 | 1 |  |
| `_resample_pcm16_mono_wav` | function | 91 | 0 | 1 |  |
| `inspect_pcm16_mono_wav` | function | 63 | 0 | 5 |  |
| `parse_recognition_batch_request` | function | 59 | 0 | 1 |  |
| `_recognition_authorization_binding` | function | 59 | 0 | 1 |  |
| `parse_synthesis_batch_request` | function | 57 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `_canonical_pcm16_mono_wav` | function | 52 | 0 | 2 |  |
| `_parse_common` | function | 50 | 0 | 2 |  |
| `_parse_recognition_segment` | function | 50 | 0 | 2 |  |
| `_synthesis_authorization_binding` | function | 42 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `_scope` | function | 34 | 0 | 2 |  |
| `_decode_base64` | function | 32 | 0 | 1 |  |
| `_parse_transforms` | function | 31 | 0 | 1 |  |
| `_combine_recognition_segments` | function | 29 | 0 | 1 |  |
| `_safe_response_identity` | function | 28 | 0 | 7 |  |
| `UnavailableBatchSpeechProvider` | class | 28 | 0 | 5 |  |
| `create_environment_batch_speech_provider` | function | 27 | 2 | 0 | gateway/channel_manager/web/app_web_handlers.py, gateway/live_voice/speech_rpc.py |
| `_exact_keys` | function | 24 | 0 | 8 |  |
| `_contract_error` | function | 19 | 0 | 7 |  |
| `_fail` | function | 19 | 0 | 85 |  |
| `_required_text` | function | 16 | 0 | 24 |  |
| `_OperationEntry` | value | 16 | 0 | 7 |  |
| `_result_envelope` | function | 16 | 0 | 13 |  |
| `_validate_api_base` | function | 15 | 1 | 1 | server/live_voice/openai_streaming_speech.py |
| `SpeechAuthorizationBinding` | value | 15 | 2 | 7 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/product_authority.py |
| `SynthesisBatchRequest` | value | 14 | 1 | 6 | gateway/live_voice/dedicated_media_registration.py |
| `_REBUILT_BODY_STALE_HEADERS` | constant | 13 | 0 | 1 |  |
| `RecognitionBatchRequest` | value | 13 | 0 | 7 |  |
| `_parse_response` | function | 12 | 0 | 1 |  |
| `_provider_payload` | function | 12 | 0 | 2 |  |
| `_timeout_ms` | function | 11 | 0 | 1 |  |
| `_diagnose_batch` | function | 11 | 0 | 4 |  |
| `BatchSpeechProvider` | value | 10 | 0 | 2 |  |
| `_VoiceCommitReceipt` | value | 10 | 0 | 2 |  |
| `_positive_int` | function | 9 | 0 | 2 |  |
| `_locale` | function | 9 | 1 | 2 | gateway/live_voice/dedicated_media_registration.py |
| `PcmWavInfo` | value | 9 | 0 | 2 |  |
| `_required_dict` | function | 8 | 0 | 8 |  |
| `_non_negative_int` | function | 8 | 0 | 5 |  |

### `server/live_voice/streaming_speech.py`（2,230 行；被 5 个生产文件导入；66 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `StreamingSpeechConformance` | class | 1108 | 1 | 1 | server/live_voice/openai_streaming_speech.py |
| `_validate_recognition_support` | function | 86 | 0 | 1 |  |
| `_validate_synthesis_support` | function | 68 | 0 | 1 |  |
| `_validate_capability` | function | 64 | 0 | 1 |  |
| `SpeechResponseAuthority` | owner | 55 | 2 | 5 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/streaming_synthesis_route.py |
| `StreamingProviderCapability` | value | 53 | 2 | 5 | gateway/live_voice/streaming_synthesis_route.py, server/live_voice/openai_streaming_speech.py |
| `SpeechStreamAuthority` | owner | 49 | 1 | 5 | gateway/live_voice/dedicated_media_registration.py |
| `_validate_hypothesis` | function | 45 | 0 | 1 |  |
| `NativeStreamingSpeechProvider` | value | 44 | 3 | 0 | gateway/live_voice/streaming_speech_route.py, gateway/live_voice/streaming_synthesis_route.py, server/live_voice/openai_streaming_speech.py |
| `RecognitionTurnDetection` | value | 35 | 3 | 7 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/streaming_speech_route.py, server/live_voice/openai_streaming_speech.py |
| `ServerVadConfig` | value | 32 | 0 | 4 |  |
| `_validate_synthesis_request` | function | 24 | 0 | 1 |  |
| `_RecognitionState` | value | 19 | 0 | 8 |  |
| `require_stream_authority` | function | 16 | 3 | 7 | gateway/live_voice/streaming_speech_route.py, gateway/live_voice/streaming_synthesis_route.py, server/live_voice/openai_streaming_speech.py |
| `default_server_vad_silence_ms` | function | 16 | 0 | 1 |  |
| `StreamingSpeechSnapshot` | value | 16 | 0 | 4 |  |
| `SynthesisStreamRequest` | value | 15 | 4 | 9 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/product_streaming_synthesis.py, gateway/live_voice/streaming_synthesis_route.py |
| `_validate_recognition_ref` | function | 14 | 0 | 3 |  |
| `_validate_synthesis_ref` | function | 14 | 0 | 2 |  |
| `_stream_request_binding` | function | 13 | 0 | 2 |  |
| `_timeout_seconds` | function | 13 | 0 | 2 |  |
| `authorize_stream_request` | function | 12 | 1 | 0 | gateway/live_voice/dedicated_media_registration.py |
| `CapabilityProvenance` | value | 12 | 3 | 49 | gateway/live_voice/streaming_speech_route.py, gateway/live_voice/streaming_synthesis_route.py, server/live_voice/openai_streaming_speech.py |
| `_required_text` | function | 12 | 0 | 1 |  |
| `StreamingSynthesisEvent` | value | 11 | 2 | 9 | gateway/live_voice/streaming_synthesis_route.py, server/live_voice/openai_streaming_speech.py |
| `_SynthesisState` | value | 11 | 0 | 12 |  |
| `RecognitionTurnBoundaryEvent` | value | 10 | 2 | 4 | gateway/live_voice/streaming_speech_route.py, server/live_voice/openai_streaming_speech.py |
| `_validate_recognition_request` | function | 10 | 0 | 1 |  |
| `StreamingRecognitionEvent` | value | 9 | 2 | 4 | gateway/live_voice/streaming_speech_route.py, server/live_voice/openai_streaming_speech.py |
| `_validate_span` | function | 9 | 0 | 3 |  |
| `RecognitionProviderSupport` | value | 8 | 1 | 4 | server/live_voice/openai_streaming_speech.py |
| `_validate_response_ref` | function | 8 | 0 | 2 |  |
| `_bounded_text` | function | 8 | 0 | 7 |  |
| `_bounded_sample_count` | function | 8 | 0 | 2 |  |
| `SynthesisProviderSupport` | value | 7 | 1 | 4 | server/live_voice/openai_streaming_speech.py |
| `TextSpan` | value | 7 | 2 | 5 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/streaming_synthesis_route.py |
| `_validate_modes` | function | 7 | 0 | 2 |  |
| `_empty_synthesis_payload` | function | 7 | 0 | 3 |  |
| `_uint` | function | 7 | 0 | 19 |  |
| `_positive_int` | function | 7 | 0 | 7 |  |

### `gateway/live_voice/streaming_speech_route.py`（1,536 行；被 2 个生产文件导入；30 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `StreamingRecognitionRouteOwner` | owner | 1289 | 2 | 1 | gateway/channel_manager/web/app_web_handlers.py, gateway/live_voice/dedicated_media_registration.py |
| `StreamingRecognitionHandle` | value | 36 | 1 | 16 | gateway/live_voice/dedicated_media_registration.py |
| `_settle_eot_from_collector` | function | 25 | 0 | 1 |  |
| `StreamingRecognitionFallbackReason` | value | 11 | 1 | 30 | gateway/live_voice/dedicated_media_registration.py |
| `StreamingRecognitionEndOfTurn` | value | 11 | 1 | 5 | gateway/live_voice/dedicated_media_registration.py |
| `StreamingRecognitionSpeechStart` | value | 9 | 1 | 5 | gateway/live_voice/dedicated_media_registration.py |
| `_consume_eot_future_failure` | function | 9 | 0 | 1 |  |
| `_consume_speech_start_future_failure` | function | 9 | 0 | 1 |  |
| `_eot_collector_callback` | function | 7 | 0 | 1 |  |
| `StreamingRecognitionOutcome` | value | 6 | 1 | 7 | gateway/live_voice/dedicated_media_registration.py |
| `_RECOGNITION_SESSION_TIMEOUT_SECONDS` | constant | 3 | 0 | 1 |  |
| `_LOGGER` | constant | 1 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `_MAX_PENDING_PROVIDER_FRAMES` | constant | 1 | 0 | 2 |  |
| `_OPEN_TIMEOUT_SECONDS` | constant | 1 | 0 | 4 |  |
| `_PROVIDER_SEND_TIMEOUT_SECONDS` | constant | 1 | 0 | 1 |  |
| `_PROVIDER_COMMIT_TIMEOUT_SECONDS` | constant | 1 | 0 | 1 |  |
| `_PROVIDER_CANCEL_TIMEOUT_SECONDS` | constant | 1 | 0 | 2 |  |
| `_PROVIDER_CLOSE_TIMEOUT_SECONDS` | constant | 1 | 0 | 1 |  |
| `_PUMP_DRAIN_TIMEOUT_SECONDS` | constant | 1 | 0 | 2 |  |
| `_FINAL_TIMEOUT_SECONDS` | constant | 1 | 0 | 3 |  |
| `_PRECOMMIT_EVENT_TIMEOUT_SECONDS` | constant | 1 | 0 | 2 |  |
| `_LOCAL_TASK_CANCEL_TIMEOUT_SECONDS` | constant | 1 | 0 | 5 |  |
| `_MAX_ACTIVE_STREAMS` | constant | 1 | 0 | 1 |  |
| `_MAX_RETAINED_PROVIDER_TASKS` | constant | 1 | 0 | 1 |  |
| `_MAX_PROVIDER_CLOSE_OBLIGATIONS` | constant | 1 | 0 | 3 |  |
| `_MAX_PROVIDER_CLEANUP_TASKS` | constant | 1 | 0 | 1 |  |
| `_QUEUE_SENTINEL` | constant | 1 | 0 | 2 |  |
| `_PROCESS_CONTROL` | constant | 1 | 0 | 14 |  |
| `_T` | constant | 1 | 0 | 13 |  |
| `StreamingSpeechSelector` | constant | 1 | 0 | 1 |  |

### `server/live_voice/speech_ports.py`（477 行；被 5 个生产文件导入；19 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `RecognitionPort` | class | 165 | 1 | 1 | server/live_voice/batch_speech.py |
| `SynthesisPort` | class | 135 | 1 | 0 | server/live_voice/batch_speech.py |
| `_validate_capability` | function | 28 | 1 | 2 | server/live_voice/streaming_speech.py |
| `SynthesisRequest` | value | 8 | 1 | 2 | server/live_voice/batch_speech.py |
| `SynthesisEvent` | value | 8 | 0 | 7 |  |
| `RecognitionHypothesis` | value | 7 | 3 | 3 | server/live_voice/batch_speech.py, server/live_voice/openai_streaming_speech.py, server/live_voice/streaming_speech.py |
| `RecognitionEvent` | value | 7 | 0 | 4 |  |
| `RecognitionSession` | value | 7 | 0 | 4 |  |
| `ResolvedRecognition` | value | 6 | 0 | 2 |  |
| `SynthesisEventKind` | value | 5 | 3 | 10 | gateway/live_voice/streaming_synthesis_route.py, server/live_voice/openai_streaming_speech.py, server/live_voice/streaming_speech.py |
| `SpeechCapability` | value | 5 | 1 | 3 | server/live_voice/batch_speech.py |
| `CriticalSpeechDecision` | value | 5 | 0 | 5 |  |
| `RenderTransform` | value | 5 | 1 | 2 | server/live_voice/batch_speech.py |
| `RenderPlan` | value | 5 | 0 | 3 |  |
| `SpeechPortViolation` | exception | 4 | 1 | 27 | server/live_voice/batch_speech.py |
| `RecognitionEventKind` | value | 4 | 4 | 9 | gateway/live_voice/streaming_speech_route.py, server/live_voice/batch_speech.py, server/live_voice/openai_streaming_speech.py |
| `ProviderRef` | value | 4 | 5 | 5 | gateway/live_voice/streaming_speech_route.py, gateway/live_voice/streaming_synthesis_route.py, server/live_voice/batch_speech.py |
| `RecognitionAlternative` | value | 4 | 3 | 2 | server/live_voice/batch_speech.py, server/live_voice/openai_streaming_speech.py, server/live_voice/streaming_speech.py |
| `SpeechMode` | value | 3 | 4 | 6 | gateway/live_voice/streaming_synthesis_route.py, server/live_voice/batch_speech.py, server/live_voice/openai_streaming_speech.py |

## 04 Committed input/product authority（15 文件，16,902 行）

### `server/live_voice/p3_authenticated_composition.py`（5,435 行；被 2 个生产文件导入；55 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `P3AuthenticatedComposition` | class | 3982 | 1 | 3 | server/live_voice/product_composition_registry.py |
| `AgentManagerProjectBindingResolver` | owner | 311 | 0 | 4 |  |
| `ServerSessionProjectAuthorityResolver` | owner | 298 | 0 | 3 |  |
| `create_p3_composition_from_environment` | function | 150 | 1 | 1 | server/agent_ws_server.py |
| `StaticBearerAuthenticator` | class | 55 | 0 | 3 |  |
| `NativeP3ActivationAuthority` | value | 51 | 1 | 16 | server/live_voice/product_composition_registry.py |
| `_validated_executor_configuration` | function | 34 | 0 | 6 |  |
| `_resolve_database_path` | function | 31 | 0 | 2 |  |
| `_DirectP3RuntimeOwner` | owner | 30 | 0 | 4 |  |
| `AuthenticatedPrincipal` | value | 26 | 0 | 17 |  |
| `_product_execution_requirements` | function | 19 | 0 | 3 |  |
| `_abort_factory_owner` | function | 18 | 0 | 2 |  |
| `_parse_utc` | function | 16 | 0 | 9 |  |
| `_PreparedRetrySnapshot` | value | 16 | 0 | 5 |  |
| `PreparedProductionIntentAuthority` | value | 13 | 1 | 3 | server/live_voice/product_composition_registry.py |
| `_persisted_executor_selection` | function | 11 | 0 | 2 |  |
| `P3_PRODUCTION_MUTATIONS` | constant | 10 | 1 | 6 | server/live_voice/product_composition_registry.py |
| `P3_ROUTE_METHODS` | constant | 9 | 1 | 2 | server/agent_ws_server.py |
| `AuthorityResolver` | value | 9 | 0 | 1 |  |
| `LoggingP3TelemetrySink` | class | 9 | 0 | 2 |  |
| `_required_text` | function | 8 | 1 | 21 | server/live_voice/product_composition_registry.py |
| `_PRODUCT_DIRECT_OPERATION_VERSIONS` | constant | 7 | 0 | 2 |  |
| `_PRODUCT_DIRECT_D2_OPERATION_VERSIONS` | constant | 7 | 0 | 1 |  |
| `PreparedP3MutationConfirmation` | value | 7 | 0 | 3 |  |
| `_PRODUCT_ADMISSION_POLICY` | constant | 6 | 0 | 3 |  |
| `_ProjectSnapshot` | value | 5 | 0 | 3 |  |
| `P3RouteTelemetry` | value | 5 | 0 | 5 |  |
| `_validate_reconcile_interval` | function | 4 | 0 | 2 |  |
| `PrincipalAuthenticator` | value | 4 | 0 | 1 |  |
| `ResolvedAuthority` | value | 4 | 0 | 14 |  |
| `resolve_p3_database_path_from_environment` | function | 4 | 1 | 1 | server/agent_ws_server.py |
| `P3_QUERY_OPERATIONS` | constant | 3 | 0 | 4 |  |
| `P3_PRODUCT_AUTHORITY_OPERATIONS` | constant | 3 | 0 | 3 |  |
| `P3RouteResult` | value | 3 | 1 | 9 | server/live_voice/product_composition_registry.py |
| `_is_enabled` | function | 2 | 1 | 3 | server/live_voice/product_composition_registry.py |
| `_path_key` | function | 2 | 0 | 5 |  |
| `_earlier_expiry` | function | 2 | 0 | 2 |  |
| `P3TelemetrySink` | value | 2 | 0 | 2 |  |
| `ClosableBindingResolver` | value | 2 | 0 | 1 |  |
| `P3_MUTATIONS` | constant | 1 | 1 | 8 | server/live_voice/product_composition_registry.py |

### `server/live_voice/production_task_intent.py`（2,004 行；被 8 个生产文件导入；47 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductionMultiTaskResolver` | owner | 716 | 1 | 1 | server/live_voice/voice_task_bridge.py |
| `BoundedClarificationOwner` | owner | 177 | 2 | 3 | server/live_voice/product_composition_registry.py, server/live_voice/voice_task_bridge.py |
| `AuthenticatedTaskFact` | value | 158 | 3 | 12 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_production_intent_composition.py, server/live_voice/product_composition_registry.py |
| `ProductionOriginBinding` | value | 80 | 2 | 10 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_production_intent_composition.py |
| `ProductionTaskResolution` | value | 72 | 4 | 6 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_production_intent_composition.py, server/live_voice/product_composition_registry.py |
| `ProductionConfirmationBinding` | value | 65 | 2 | 5 | server/live_voice/p3_production_intent_composition.py, server/live_voice/product_composition_registry.py |
| `ProductionTaskIntentProposal` | value | 63 | 4 | 7 | server/live_voice/native_business_contract.py, server/live_voice/product_composition_registry.py, server/live_voice/production_task_classifier.py |
| `_build_origin_binding` | function | 53 | 0 | 2 |  |
| `_validate_arguments` | function | 50 | 1 | 2 | server/live_voice/task_semantics.py |
| `TaskAuthorityRead` | value | 49 | 3 | 4 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_production_intent_composition.py, server/live_voice/task_semantics.py |
| `ProductionTaskIntentRequest` | value | 43 | 3 | 6 | server/live_voice/native_business_router.py, server/live_voice/product_composition_registry.py, server/live_voice/voice_task_bridge.py |
| `BoundProductionFieldExtraction` | value | 26 | 0 | 4 |  |
| `ClarificationAnswer` | value | 24 | 1 | 3 | server/live_voice/product_composition_registry.py |
| `_canonical_mapping` | function | 19 | 0 | 5 |  |
| `_ZERO_EFFECTS` | constant | 17 | 0 | 1 |  |
| `_ARGUMENT_FIELDS` | constant | 16 | 2 | 1 | server/live_voice/production_task_classifier.py, server/live_voice/task_semantics.py |
| `ClarificationHandle` | value | 16 | 0 | 4 |  |
| `ProductionFieldExtraction` | value | 15 | 1 | 3 | server/live_voice/task_semantics.py |
| `_semantic_context_binding` | function | 15 | 0 | 2 |  |
| `ProductionTaskAuthorityReader` | value | 14 | 1 | 3 | server/live_voice/voice_task_bridge.py |
| `TrustedConfirmationConsumptionReceipt` | value | 13 | 2 | 3 | server/live_voice/p3_production_intent_composition.py, server/live_voice/product_composition_registry.py |
| `_proposal_field_value` | function | 13 | 0 | 1 |  |
| `_structured_semantic_digest` | function | 11 | 0 | 1 |  |
| `_MATERIAL_OPERATIONS` | constant | 10 | 0 | 1 |  |
| `_require_text` | function | 10 | 0 | 5 |  |
| `_require_opaque` | function | 10 | 0 | 24 |  |
| `TrustedProductionOriginReceipt` | value | 10 | 1 | 5 | server/live_voice/p3_production_intent_composition.py |
| `_expected_extraction_fields` | function | 10 | 0 | 1 |  |
| `build_production_origin_binding` | function | 8 | 2 | 1 | server/live_voice/native_business_router.py, server/live_voice/product_composition_registry.py |
| `_QUERY_KIND` | constant | 7 | 2 | 2 | server/live_voice/production_task_classifier.py, server/live_voice/task_semantics.py |
| `ProductionTaskPolicyOutcome` | value | 7 | 4 | 48 | server/live_voice/native_business_router.py, server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_production_intent_composition.py |
| `_require_persistent_identity` | function | 7 | 0 | 7 |  |
| `_UNSPECIFIED_COLLECTION_CAPABILITY_DIGEST` | constant | 7 | 0 | 1 |  |
| `_UNSPECIFIED_CONTEXT_FINGERPRINT` | constant | 7 | 0 | 2 |  |
| `_UNSPECIFIED_MODEL_BINDING_FINGERPRINT` | constant | 7 | 0 | 2 |  |
| `ProductionOriginAuthority` | value | 6 | 1 | 2 | server/live_voice/voice_task_bridge.py |
| `ProductionConfirmationConsumer` | value | 6 | 1 | 2 | server/live_voice/voice_task_bridge.py |
| `ProductionIntentOrigin` | value | 4 | 4 | 12 | server/live_voice/native_business_router.py, server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_production_intent_composition.py |
| `_aware_utc` | function | 4 | 0 | 2 |  |
| `_ClarificationEntry` | value | 3 | 0 | 2 |  |

### `server/live_voice/unified_committed_input.py`（1,694 行；被 2 个生产文件导入；5 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SqliteUnifiedCommittedInputJournal` | owner | 1622 | 2 | 2 | server/live_voice/product_composition_registry.py, server/live_voice/semantic_continuity.py |
| `PendingSemanticContext` | value | 9 | 1 | 8 | server/live_voice/semantic_continuity.py |
| `UnifiedForegroundEffectAdmission` | value | 6 | 0 | 12 |  |
| `UnifiedInputAdmission` | value | 5 | 0 | 6 |  |
| `SEMANTIC_PROPOSAL_TTL_SECONDS` | constant | 1 | 1 | 1 | server/live_voice/semantic_continuity.py |

### `server/live_voice/critical_token_safety.py`（1,397 行；被 1 个生产文件导入；32 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `CriticalTokenSafetyGate` | owner | 575 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `CriticalTokenPolicy` | class | 244 | 0 | 3 |  |
| `_PATTERNS` | constant | 176 | 0 | 1 |  |
| `CommittedSpeechCandidate` | value | 56 | 1 | 13 | server/live_voice/product_composition_registry.py |
| `CriticalTokenReason` | value | 22 | 0 | 37 |  |
| `SpeechAlternativeEvidence` | value | 22 | 1 | 4 | server/live_voice/product_composition_registry.py |
| `_candidate_fingerprint` | function | 22 | 0 | 2 |  |
| `_matches_clarification_provenance` | function | 19 | 0 | 1 |  |
| `_matches_input_generation_provenance` | function | 13 | 0 | 3 |  |
| `CriticalTokenKind` | value | 10 | 0 | 29 |  |
| `CriticalTokenDecision` | value | 9 | 0 | 10 |  |
| `ClarificationRequirement` | value | 9 | 0 | 5 |  |
| `_blocked_result` | function | 9 | 0 | 22 |  |
| `CriticalTokenObservation` | value | 8 | 0 | 9 |  |
| `DispatchAuthorization` | value | 8 | 0 | 6 |  |
| `CriticalTokenSafetyViolation` | exception | 6 | 0 | 24 |  |
| `InteractionFenceResult` | value | 6 | 0 | 3 |  |
| `CriticalTokenDecisionStatus` | value | 5 | 1 | 22 | server/live_voice/product_composition_registry.py |
| `ClarificationState` | value | 5 | 0 | 16 |  |
| `AuthorizationState` | value | 5 | 0 | 19 |  |
| `ProtectedRoute` | value | 5 | 1 | 5 | server/live_voice/product_composition_registry.py |
| `GuardDispatchResult` | value | 5 | 0 | 9 |  |
| `GuardDispatchStatus` | value | 4 | 1 | 9 | server/live_voice/product_composition_registry.py |
| `CriticalTokenGateResult` | value | 4 | 0 | 14 |  |
| `_ClarificationRecord` | value | 4 | 0 | 2 |  |
| `_AuthorizationRecord` | value | 4 | 0 | 2 |  |
| `_normalize_comparison_token` | function | 4 | 0 | 1 |  |
| `EvidenceSource` | value | 3 | 1 | 7 | server/live_voice/product_composition_registry.py |
| `EvidenceTextKind` | value | 3 | 0 | 6 |  |
| `_stable_id` | function | 3 | 0 | 2 |  |
| `_normalize_token` | function | 2 | 0 | 2 |  |
| `_commit_fingerprint` | function | 2 | 0 | 1 |  |

### `server/live_voice/product_authority.py`（1,302 行；被 5 个生产文件导入；45 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductAuthorityService` | owner | 311 | 2 | 7 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py |
| `P3AuthorityAdapter` | owner | 192 | 2 | 1 | server/live_voice/product_composition_registry.py, server/live_voice/product_p3_text_adapter.py |
| `ResolvedProductAuthority` | value | 91 | 3 | 11 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py, server/live_voice/product_observability_runtime.py |
| `AuthorityDecision` | value | 56 | 0 | 10 |  |
| `_EVIDENCE_IDS` | constant | 43 | 0 | 1 |  |
| `TrustedAuthorityCandidate` | value | 43 | 2 | 6 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py |
| `SpeechAuthorityResolverAdapter` | owner | 42 | 0 | 1 |  |
| `P3AuthorityContext` | value | 34 | 2 | 6 | server/live_voice/product_composition_registry.py, server/live_voice/product_p3_text_adapter.py |
| `AuthorityRouteContext` | value | 31 | 3 | 7 | server/live_voice/product_composition_registry.py, server/live_voice/product_p2_interaction_adapter.py, server/live_voice/product_p3_text_adapter.py |
| `P2AuthorityAdapter` | owner | 29 | 2 | 1 | server/live_voice/product_composition_registry.py, server/live_voice/product_p2_interaction_adapter.py |
| `ProductAuthorityRequest` | value | 26 | 1 | 9 | server/live_voice/product_composition_registry.py |
| `AuthorityConfirmationBinding` | value | 23 | 0 | 7 |  |
| `TrustedAuthorityLookup` | value | 20 | 1 | 3 | server/live_voice/product_composition_registry.py |
| `AuthorityDecisionReason` | value | 19 | 0 | 39 |  |
| `_P3_OPERATIONS` | constant | 18 | 0 | 2 |  |
| `_P3_TARGETED_OPERATIONS` | constant | 16 | 0 | 3 |  |
| `AuthorityResourceBinding` | value | 16 | 2 | 15 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_p3_text_adapter.py |
| `P2AuthenticatedContext` | value | 16 | 2 | 4 | server/live_voice/product_composition_registry.py, server/live_voice/product_p2_interaction_adapter.py |
| `AuthorityConfirmationRequest` | value | 14 | 0 | 5 |  |
| `AuthorityRoutingClaim` | value | 13 | 0 | 4 |  |
| `_P3_MUTATIONS` | constant | 11 | 0 | 2 |  |
| `_require_text` | function | 10 | 1 | 37 | server/live_voice/product_p2_interaction_adapter.py |
| `_parse_utc` | function | 9 | 1 | 11 | server/live_voice/p3_authenticated_composition.py |
| `_authorized_or_none` | function | 9 | 0 | 3 |  |
| `_normalize_scope` | function | 7 | 0 | 7 |  |
| `_normalize_context_ref` | function | 7 | 0 | 2 |  |
| `_decision` | function | 7 | 0 | 11 |  |
| `ProductAuthorityUnavailable` | exception | 6 | 2 | 2 | server/live_voice/product_p2_interaction_adapter.py, server/live_voice/product_p3_text_adapter.py |
| `_require_string_set` | function | 6 | 0 | 5 |  |
| `_require_source` | function | 5 | 0 | 6 |  |
| `_normalize_now` | function | 5 | 0 | 1 |  |
| `AuthorityDecisionStatus` | value | 4 | 1 | 21 | server/live_voice/product_composition_registry.py |
| `_optional_text` | function | 4 | 0 | 10 |  |
| `_require_sha256` | function | 4 | 0 | 7 |  |
| `TrustedAuthorityResolver` | value | 4 | 0 | 3 |  |
| `ProductAuthorityInputError` | exception | 2 | 0 | 11 |  |
| `_input_error` | function | 2 | 0 | 44 |  |
| `_utc_now` | function | 2 | 1 | 1 | server/live_voice/product_p2_interaction_adapter.py |
| `_MAX_ID_LENGTH` | constant | 1 | 0 | 1 |  |
| `_MAX_SOURCE_LENGTH` | constant | 1 | 0 | 1 |  |

### `server/live_voice/task_semantics.py`（1,210 行；被 4 个生产文件导入；18 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `TaskSemanticResolver` | owner | 362 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `task_semantic_output_schema` | function | 304 | 0 | 1 |  |
| `_INSTRUCTIONS` | constant | 177 | 0 | 1 |  |
| `TaskSemanticDecision` | value | 132 | 4 | 4 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py, server/live_voice/semantic_continuity.py |
| `TaskSemanticContext` | value | 83 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `_structural_feedback` | function | 29 | 0 | 1 |  |
| `_OUTPUT_FIELDS` | constant | 14 | 0 | 4 |  |
| `_STRUCTURAL_RETRY_INSTRUCTIONS` | constant | 10 | 0 | 2 |  |
| `_text` | function | 9 | 0 | 14 |  |
| `_object` | function | 7 | 0 | 1 |  |
| `_INVOCATION_OPTIONS` | constant | 5 | 0 | 1 |  |
| `_fail` | function | 4 | 1 | 20 | server/live_voice/semantic_continuity.py |
| `_digest` | function | 2 | 0 | 5 |  |
| `_invalid_constant` | function | 2 | 0 | 1 |  |
| `_MAX_INPUT_BYTES` | constant | 1 | 0 | 1 |  |
| `_MAX_CONTEXT_BYTES` | constant | 1 | 0 | 1 |  |
| `_MAX_OUTPUT_BYTES` | constant | 1 | 0 | 1 |  |
| `_TIMEOUT_SECONDS` | constant | 1 | 0 | 2 |  |

### `server/live_voice/p3_confirmation.py`（979 行；被 7 个生产文件导入；19 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SqliteP3ConfirmationLedger` | owner | 418 | 2 | 3 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_production_intent_composition.py |
| `BoundedP3ConfirmationOwner` | owner | 153 | 3 | 2 | server/agent_ws_server.py, server/live_voice/p3_product_confirmation.py, server/live_voice/product_composition_registry.py |
| `p3_confirmation_intent_fingerprint` | function | 83 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `PreparedP3RetryFacts` | value | 80 | 1 | 3 | server/live_voice/p3_authenticated_composition.py |
| `P3ConfirmationBinding` | value | 37 | 5 | 11 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_product_confirmation.py, server/live_voice/p3_production_intent_composition.py |
| `TrustedP3ConfirmationIssue` | value | 32 | 1 | 5 | server/live_voice/product_composition_registry.py |
| `P3ConfirmationOwnerContext` | value | 24 | 2 | 8 | server/live_voice/p3_product_confirmation.py, server/live_voice/product_composition_registry.py |
| `_parse_utc` | function | 16 | 2 | 9 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_authority.py |
| `_validate_capacity` | function | 12 | 0 | 2 |  |
| `_P3_MUTATION_OPERATIONS` | constant | 11 | 0 | 2 |  |
| `P3ConfirmationVerifier` | value | 8 | 2 | 2 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_product_confirmation.py |
| `ValidatedP3ConfirmationForwarding` | value | 7 | 3 | 4 | server/live_voice/p3_product_confirmation.py, server/live_voice/p3_production_intent_composition.py, server/live_voice/product_composition_registry.py |
| `_scope_key` | function | 6 | 0 | 5 |  |
| `IssuedP3Confirmation` | value | 6 | 0 | 5 |  |
| `VerifiedP3Confirmation` | value | 4 | 4 | 4 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_product_confirmation.py, server/live_voice/p3_production_intent_composition.py |
| `P3_CONFIRMATION_MAX_TTL` | constant | 1 | 2 | 2 | server/live_voice/product_composition_registry.py, server/live_voice/unified_committed_input.py |
| `P3_CONFIRMATION_MAX_CAPACITY` | constant | 1 | 1 | 4 | server/live_voice/unified_committed_input.py |
| `_P3_TARGETED_MUTATION_OPERATIONS` | constant | 1 | 0 | 1 |  |
| `_P3_RETRY_ELIGIBLE_OUTCOMES` | constant | 1 | 0 | 1 |  |

### `server/live_voice/p3_production_intent_composition.py`（880 行；被 3 个生产文件导入；10 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `StoreProductionTaskAuthorityReader` | owner | 519 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `CallLocalProductionConfirmationConsumer` | class | 171 | 2 | 1 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py |
| `CallLocalProductionOriginAuthority` | owner | 66 | 3 | 1 | server/live_voice/native_business_router.py, server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py |
| `_NO_EXECUTOR_PROFILE_DIGEST` | constant | 9 | 0 | 2 |  |
| `production_model_binding_fingerprint` | function | 9 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `CallLocalProductionConfirmationClaim` | value | 8 | 1 | 3 | server/live_voice/p3_authenticated_composition.py |
| `production_context_fingerprint` | function | 6 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `_reader_violation` | function | 6 | 0 | 27 |  |
| `_QUERY_OPERATIONS` | constant | 3 | 0 | 1 |  |
| `_AUTHORITY_SNAPSHOT_CONVERGENCE_ATTEMPTS` | constant | 1 | 0 | 2 |  |

### `server/live_voice/voice_task_policy.py`（739 行；被 4 个生产文件导入；5 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `FormalTaskPolicyAdapter` | owner | 591 | 2 | 2 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_p3_text_adapter.py |
| `FormalTaskPolicyInput` | value | 70 | 2 | 7 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_p3_text_adapter.py |
| `FORMAL_TASK_MUTATION_OPERATIONS` | constant | 13 | 2 | 2 | server/live_voice/production_task_classifier.py, server/live_voice/production_task_intent.py |
| `FormalTaskInvocation` | value | 4 | 0 | 3 |  |
| `FORMAL_TASK_QUERY_OPERATIONS` | constant | 3 | 2 | 3 | server/live_voice/production_task_classifier.py, server/live_voice/production_task_intent.py |

### `channels/web/frontend/src/features/live-voice/formal/unifiedCommittedInputOwner.ts`（299 行；被 1 个生产文件导入；8 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductUnifiedCommittedInputOwner` | class | 85 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `UnifiedAuthoritativeFinal` | type | 8 | 1 | 4 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `UnifiedCommittedInputBinding` | type | 7 | 0 | 2 |  |
| `UnifiedCommittedInputRequest` | type | 5 | 0 | 2 |  |
| `UnifiedSupersededResponse` | type | 4 | 0 | 1 |  |
| `PRODUCT_UNIFIED_COMMITTED_INPUT_METHOD` | const | 1 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_SEMANTIC_CLIENT_TIMEOUT_MS` | const | 1 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `UnifiedCommittedText` | type | 1 | 0 | 2 |  |

### `server/live_voice/semantic_continuity.py`（255 行；被 1 个生产文件导入；3 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SemanticContinuity` | class | 213 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_fail` | function | 4 | 0 | 7 |  |
| `SemanticCall` | constant | 1 | 0 | 1 |  |

### `server/live_voice/p3_model_resolution.py`（222 行；被 6 个生产文件导入；4 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ServerModelCatalogResolver` | owner | 169 | 2 | 1 | server/agent_ws_server.py, server/runtime/agent_adapter/interface_deep.py |
| `P3ModelResolver` | value | 9 | 3 | 1 | server/live_voice/native_agent_model.py, server/live_voice/p3_authenticated_composition.py, server/live_voice/task_semantics.py |
| `_CatalogEntry` | value | 7 | 0 | 6 |  |
| `ResolvedP3Model` | value | 5 | 2 | 5 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_confirmation.py |

### `server/live_voice/voice_task_bridge.py`（197 行；被 4 个生产文件导入；5 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `VoiceTaskBridge` | owner | 123 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `TaskIntent` | value | 13 | 0 | 2 |  |
| `UnifiedCommittedInputRoute` | value | 11 | 4 | 1 | gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_business_router.py, server/live_voice/native_interaction_runtime.py |
| `VoiceTaskBridgeViolation` | exception | 5 | 0 | 14 |  |
| `TaskIntentDisposition` | value | 4 | 1 | 1 | server/live_voice/product_composition_registry.py |

### `server/live_voice/production_task_classifier.py`（162 行；被 1 个生产文件导入；8 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductionTaskIntentClassifier` | class | 83 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `_strict_json_object` | function | 21 | 0 | 1 |  |
| `_ARGUMENT_FIELDS` | constant | 16 | 0 | 1 |  |
| `_QUERY_KIND` | constant | 7 | 0 | 2 |  |
| `_require_source_facts` | function | 6 | 0 | 1 |  |
| `_OPERATIONS` | constant | 1 | 0 | 1 |  |
| `_STRUCTURED_FIELDS` | constant | 1 | 0 | 1 |  |
| `_PRIORITIES` | constant | 1 | 0 | 1 |  |

### `server/live_voice/p3_product_confirmation.py`（127 行；被 3 个生产文件导入；2 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductP3ConfirmationForwarder` | class | 72 | 3 | 1 | server/agent_ws_server.py, server/live_voice/p3_production_intent_composition.py, server/live_voice/product_composition_registry.py |
| `_ForwardingPermit` | value | 17 | 0 | 2 |  |

## 05 Conversation Runtime（5 文件，8,395 行）

### `server/live_voice/agent_conversation_runtime.py`（5,089 行；被 4 个生产文件导入；41 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `AgentConversationRuntime` | owner | 4442 | 2 | 0 | server/live_voice/native_business_router.py, server/live_voice/product_composition_registry.py |
| `_BoundedNotificationBuffer` | class | 215 | 0 | 1 |  |
| `AgentConversationRuntimeSnapshot` | value | 30 | 0 | 2 |  |
| `FormalHistoryWriter` | value | 27 | 0 | 1 |  |
| `AgentGenerationInterruption` | value | 21 | 1 | 9 | server/live_voice/product_p2_interaction_adapter.py |
| `_ResponseOutputState` | value | 13 | 0 | 6 |  |
| `AgentConversationNotification` | value | 11 | 1 | 14 | server/live_voice/product_p2_interaction_adapter.py |
| `AgentConversationEffectClaim` | value | 9 | 0 | 2 |  |
| `_ConversationEffectClaimEntry` | value | 9 | 0 | 3 |  |
| `AgentConversationNotificationLease` | value | 7 | 0 | 13 |  |
| `AgentConversationEffectAckResult` | value | 7 | 0 | 2 |  |
| `_AdmissionEntry` | value | 7 | 0 | 5 |  |
| `AgentConversationHandle` | value | 6 | 1 | 10 | server/live_voice/product_p2_interaction_adapter.py |
| `PresentationAckResult` | value | 6 | 3 | 5 | server/live_voice/presentation_ledger.py, server/live_voice/product_composition_registry.py, server/live_voice/product_p2_interaction_adapter.py |
| `_TaskPresentationReservation` | value | 6 | 0 | 3 |  |
| `AgentConversationRuntimeViolation` | exception | 5 | 0 | 184 |  |
| `GenerationInterruptionFenceStatus` | value | 5 | 0 | 3 |  |
| `AuthoritativePresentationHandle` | value | 5 | 2 | 4 | server/live_voice/product_composition_registry.py, server/live_voice/product_p2_interaction_adapter.py |
| `_CommittedTurnSubmissionEntry` | value | 5 | 0 | 3 |  |
| `_NotificationLeaseRecord` | value | 5 | 0 | 10 |  |
| `_TurnIdentityClaim` | value | 5 | 0 | 7 |  |
| `AgentConversationShutdownStatus` | value | 4 | 1 | 8 | server/live_voice/product_p2_interaction_adapter.py |
| `AgentConversationShutdownResult` | value | 4 | 1 | 10 | server/live_voice/product_p2_interaction_adapter.py |
| `_ClosedTaskPresentationReservation` | value | 4 | 0 | 3 |  |
| `_PresentationAckEntry` | value | 4 | 0 | 5 |  |
| `_QueuedNotification` | value | 3 | 0 | 5 |  |
| `_AdmissionOutcome` | value | 3 | 0 | 10 |  |
| `_NotificationBufferClosed` | exception | 2 | 0 | 3 |  |
| `_NotificationConsumerDetached` | exception | 2 | 0 | 4 |  |
| `_MAX_NOTIFICATION_CONSUMER_ID_CHARS` | constant | 1 | 0 | 2 |  |
| `_MAX_NOTIFICATION_CONSUMER_ID_UTF8_BYTES` | constant | 1 | 0 | 2 |  |
| `_MAX_NOTIFICATION_BATCH` | constant | 1 | 1 | 1 | server/live_voice/product_p2_interaction_adapter.py |
| `_MAX_EFFECT_ID_CHARS` | constant | 1 | 0 | 2 |  |
| `_MAX_EFFECT_ID_UTF8_BYTES` | constant | 1 | 0 | 2 |  |
| `_MAX_EFFECTS_PER_REQUEST` | constant | 1 | 0 | 1 |  |
| `_MAX_FORMAL_CONTEXT_ENTRIES` | constant | 1 | 0 | 1 |  |
| `_MAX_FORMAL_CONTEXT_UTF8_BYTES` | constant | 1 | 0 | 1 |  |
| `_DEFAULT_NATIVE_DELEGATE_TIMEOUT_SECONDS` | constant | 1 | 0 | 1 |  |
| `_MAX_NATIVE_DELEGATE_TIMEOUT_SECONDS` | constant | 1 | 0 | 1 |  |
| `_NATIVE_DELEGATE_CANCEL_SETTLEMENT_SECONDS` | constant | 1 | 0 | 1 |  |

### `server/live_voice/conversation_runtime_loop.py`（1,559 行；被 4 个生产文件导入；14 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ConversationRuntimeLoop` | owner | 1392 | 2 | 0 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py |
| `GenerationInterruptionResult` | value | 16 | 1 | 8 | server/live_voice/agent_conversation_runtime.py |
| `ConversationEffect` | value | 11 | 1 | 16 | server/live_voice/agent_conversation_runtime.py |
| `ConversationRuntimeLoopSnapshot` | value | 11 | 1 | 2 | server/live_voice/agent_conversation_runtime.py |
| `_RetainedGenerationInterrupt` | value | 7 | 0 | 4 |  |
| `ResponseCancelResult` | value | 6 | 1 | 9 | server/live_voice/agent_conversation_runtime.py |
| `PresentationHistoryIntent` | value | 6 | 2 | 4 | server/live_voice/agent_conversation_runtime.py, server/live_voice/formal_history_writer.py |
| `ConversationRuntimeLoopViolation` | exception | 5 | 1 | 48 | server/live_voice/agent_conversation_runtime.py |
| `BargeInResult` | value | 5 | 2 | 8 | server/live_voice/agent_conversation_runtime.py, server/live_voice/product_p2_interaction_adapter.py |
| `EffectState` | value | 4 | 0 | 10 |  |
| `EffectRecord` | value | 4 | 0 | 3 |  |
| `_QueuedOperation` | value | 4 | 0 | 6 |  |
| `PresentedHistoryContent` | value | 3 | 0 | 3 |  |
| `_MAX_RETAINED_GENERATION_INTERRUPTS` | constant | 1 | 0 | 3 |  |

### `server/live_voice/conversation_runtime.py`（686 行；被 3 个生产文件导入；12 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ConversationRuntime` | owner | 558 | 1 | 0 | server/live_voice/conversation_runtime_loop.py |
| `RuntimeEvent` | value | 25 | 1 | 16 | server/live_voice/conversation_runtime_loop.py |
| `ResponseRecord` | value | 7 | 1 | 5 | server/live_voice/conversation_runtime_loop.py |
| `ConversationSnapshot` | value | 6 | 1 | 2 | server/live_voice/conversation_runtime_loop.py |
| `ConversationRuntimeViolation` | exception | 5 | 1 | 22 | server/live_voice/agent_conversation_runtime.py |
| `ResponseState` | value | 5 | 3 | 6 | server/live_voice/agent_conversation_runtime.py, server/live_voice/conversation_runtime_loop.py, server/live_voice/native_interaction_runtime.py |
| `CancelState` | value | 5 | 2 | 13 | server/live_voice/agent_conversation_runtime.py, server/live_voice/conversation_runtime_loop.py |
| `TurnRecord` | value | 5 | 0 | 4 |  |
| `RuntimeEffect` | value | 5 | 0 | 4 |  |
| `InteractionState` | value | 4 | 3 | 7 | server/live_voice/agent_conversation_runtime.py, server/live_voice/conversation_runtime_loop.py, server/live_voice/native_interaction_runtime.py |
| `TurnState` | value | 4 | 2 | 15 | server/live_voice/agent_conversation_runtime.py, server/live_voice/conversation_runtime_loop.py |
| `InteractionRecord` | value | 3 | 0 | 4 |  |

### `server/live_voice/interaction_engine.py`（602 行；被 5 个生产文件导入；31 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ScriptedCascadeInteractionEngine` | owner | 250 | 0 | 0 |  |
| `InteractionEnginePort` | owner | 112 | 4 | 0 | server/live_voice/native_interaction_carrier.py, server/live_voice/openai_realtime_native_engine.py, server/live_voice/product_composition_registry.py |
| `_canonical_scope` | function | 28 | 0 | 4 |  |
| `CascadeObservationKind` | value | 19 | 0 | 16 |  |
| `_cascade_action_id` | function | 17 | 0 | 1 |  |
| `CASCADE_GOLDEN_SCRIPT` | constant | 12 | 0 | 1 |  |
| `_is_canonical_text` | function | 12 | 0 | 8 |  |
| `CascadeActionOperation` | value | 10 | 0 | 11 |  |
| `_require_canonical_identity` | function | 10 | 0 | 3 |  |
| `CascadeObservation` | value | 9 | 0 | 4 |  |
| `ScriptedCascadeSnapshot` | value | 8 | 0 | 2 |  |
| `_require_safe_integer` | function | 7 | 0 | 4 |  |
| `InteractionAction` | value | 6 | 4 | 10 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/native_interaction_carrier.py, server/live_voice/openai_realtime_native_engine.py |
| `InteractionEngineViolation` | exception | 4 | 1 | 36 | server/live_voice/openai_realtime_native_engine.py |
| `CASCADE_ACTION_OPERATIONS` | constant | 3 | 0 | 3 |  |
| `_CascadeRecord` | value | 3 | 0 | 3 |  |
| `_CascadeIdentityBinding` | value | 3 | 0 | 3 |  |
| `_MAX_OPERATION_COUNT` | constant | 1 | 0 | 1 |  |
| `_MAX_OPERATION_CHARS` | constant | 1 | 0 | 2 |  |
| `_MAX_OPERATION_UTF8_BYTES` | constant | 1 | 0 | 2 |  |
| `_MAX_IDENTITY_CHARS` | constant | 1 | 2 | 4 | server/live_voice/native_interaction_carrier.py, server/live_voice/openai_realtime_native_engine.py |
| `_MAX_IDENTITY_UTF8_BYTES` | constant | 1 | 1 | 4 | server/live_voice/openai_realtime_native_engine.py |
| `_MAX_PAYLOAD_ENTRIES` | constant | 1 | 0 | 1 |  |
| `_MAX_PAYLOAD_KEY_CHARS` | constant | 1 | 0 | 1 |  |
| `_MAX_PAYLOAD_KEY_UTF8_BYTES` | constant | 1 | 0 | 1 |  |
| `_MAX_PAYLOAD_VALUE_CHARS` | constant | 1 | 0 | 1 |  |
| `_MAX_PAYLOAD_VALUE_UTF8_BYTES` | constant | 1 | 0 | 1 |  |
| `_MAX_ACTIONS` | constant | 1 | 0 | 1 |  |
| `_MAX_OBSERVATIONS` | constant | 1 | 0 | 3 |  |
| `INTERACTION_ACTION_OPERATIONS` | constant | 1 | 3 | 0 | server/live_voice/native_interaction_carrier.py, server/live_voice/openai_realtime_native_engine.py, server/live_voice/product_composition_registry.py |
| `_CASCADE_ACTION_BY_OBSERVATION` | constant | 1 | 0 | 2 |  |

### `server/live_voice/speculative_dialogue.py`（459 行；被 2 个生产文件导入；12 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SpeculativeDialogue` | class | 305 | 2 | 4 | server/live_voice/agent_conversation_runtime.py, server/live_voice/product_composition_registry.py |
| `AttachedFormalFacade` | class | 32 | 1 | 1 | server/live_voice/agent_conversation_runtime.py |
| `facade_supports_speculation` | function | 19 | 1 | 2 | server/live_voice/agent_conversation_runtime.py |
| `SpeculativeFormalFacade` | value | 14 | 0 | 2 |  |
| `_context_signature` | function | 6 | 0 | 2 |  |
| `_chunk_bytes` | function | 6 | 0 | 1 |  |
| `SpeculativeDialogueViolation` | exception | 5 | 1 | 8 | server/live_voice/agent_conversation_runtime.py |
| `speculative_session_id` | function | 2 | 1 | 1 | server/live_voice/agent_conversation_runtime.py |
| `_LOGGER` | constant | 1 | 0 | 5 |  |
| `SPECULATION_MAX_CHUNKS` | constant | 1 | 0 | 2 |  |
| `SPECULATION_MAX_BYTES` | constant | 1 | 0 | 3 |  |
| `_SPECULATIVE_SESSION_PREFIX` | constant | 1 | 0 | 2 |  |

## 06 Agent bridge（6 文件，3,078 行）

### `server/live_voice/agent_bridge_runtime.py`（1,240 行；被 2 个生产文件导入；18 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `AgentBridgeRuntime` | owner | 862 | 1 | 1 | server/live_voice/agent_conversation_runtime.py |
| `project_round_work_progress` | function | 83 | 0 | 2 |  |
| `AgentRoundRequest` | value | 49 | 1 | 10 | server/live_voice/jiuwenswarm_agent_adapter.py |
| `AgentBridgeDispatchReservation` | value | 36 | 1 | 8 | server/live_voice/agent_conversation_runtime.py |
| `AgentBridgeCompletionHandle` | owner | 28 | 1 | 3 | server/live_voice/agent_conversation_runtime.py |
| `_validate_runtime_text` | function | 15 | 0 | 6 |  |
| `AgentBridgeRuntimeSnapshot` | value | 10 | 1 | 3 | server/live_voice/agent_conversation_runtime.py |
| `AgentBridgeCompletion` | value | 9 | 0 | 8 |  |
| `_SOURCE_ACCEPTED` | constant | 9 | 0 | 1 |  |
| `AgentBridgeRuntimeViolation` | exception | 5 | 1 | 42 | server/live_voice/agent_conversation_runtime.py |
| `AgentBridgeReservationState` | value | 5 | 0 | 21 |  |
| `AgentRoundAdapter` | value | 4 | 0 | 4 |  |
| `WorkProgressDelivery` | value | 4 | 1 | 3 | server/live_voice/agent_conversation_runtime.py |
| `AgentBridgeCompletionStatus` | value | 3 | 1 | 4 | server/live_voice/agent_conversation_runtime.py |
| `AgentBridgeSubmission` | value | 3 | 0 | 6 |  |
| `AgentEventDelivery` | value | 3 | 1 | 3 | server/live_voice/agent_conversation_runtime.py |
| `_PendingDispatch` | value | 3 | 0 | 3 |  |
| `AgentBridgeDelivery` | constant | 1 | 0 | 4 |  |

### `server/live_voice/jiuwenswarm_round_harness.py`（1,151 行；被 2 个生产文件导入；18 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `JiuWenSwarmRoundHarness` | owner | 811 | 1 | 1 | server/live_voice/agent_conversation_runtime.py |
| `HarnessRoundHandle` | owner | 149 | 2 | 11 | server/live_voice/agent_conversation_runtime.py, server/live_voice/jiuwenswarm_agent_adapter.py |
| `HarnessRoundBinding` | value | 26 | 1 | 3 | server/live_voice/agent_conversation_runtime.py |
| `_require_text` | function | 16 | 0 | 9 |  |
| `_RoundRecord` | value | 13 | 0 | 4 |  |
| `_CONTROL_MARKUP_TRANSLATION` | constant | 9 | 0 | 1 |  |
| `HarnessRoundSnapshot` | value | 9 | 1 | 2 | server/live_voice/agent_conversation_runtime.py |
| `RoundCancelResult` | value | 8 | 1 | 5 | server/live_voice/agent_conversation_runtime.py |
| `HarnessRoundReservation` | value | 7 | 1 | 13 | server/live_voice/agent_conversation_runtime.py |
| `_ReservationRecord` | value | 7 | 0 | 4 |  |
| `HarnessReservationState` | value | 6 | 0 | 24 |  |
| `FormalAgentFacade` | value | 6 | 1 | 5 | server/live_voice/agent_conversation_runtime.py |
| `HarnessRoundViolation` | exception | 5 | 2 | 45 | server/live_voice/agent_conversation_runtime.py, server/live_voice/jiuwenswarm_agent_adapter.py |
| `_NO_TOOL_DSML_MARKUP` | constant | 4 | 0 | 1 |  |
| `_contains_no_tool_control_markup` | function | 3 | 0 | 1 |  |
| `_ROUND_CONTROL_QUEUE_RESERVE` | constant | 1 | 0 | 1 |  |
| `_NO_TOOL_OUTPUT_BUFFER_MAX_BYTES` | constant | 1 | 0 | 1 |  |
| `_END` | constant | 1 | 0 | 3 |  |

### `server/runtime/agent_adapter/formal_live_voice.py`（401 行；被 12 个生产文件导入；8 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `FormalAgentExecution` | value | 173 | 4 | 0 | server/live_voice/agent_conversation_runtime.py, server/live_voice/jiuwenswarm_round_harness.py, server/live_voice/speculative_dialogue.py |
| `FormalContextSnapshot` | value | 55 | 7 | 1 | server/live_voice/agent_conversation_runtime.py, server/live_voice/jiuwenswarm_round_harness.py, server/live_voice/native_business_context.py |
| `PresentedAgentAnalysis` | value | 42 | 4 | 0 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py, server/live_voice/product_p2_interaction_adapter.py |
| `FORMAL_VOICE_PRESENTATION_INSTRUCTIONS` | constant | 41 | 1 | 0 | server/runtime/agent_adapter/interface_deep.py |
| `NATIVE_ANALYSIS_PRESENTATION_INSTRUCTIONS` | constant | 21 | 1 | 0 | server/runtime/agent_adapter/interface_deep.py |
| `_require_text` | function | 14 | 2 | 7 | server/live_voice/jiuwenswarm_round_harness.py, server/live_voice/product_p2_interaction_adapter.py |
| `FormalContextEntry` | value | 13 | 3 | 2 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_business_context.py, server/live_voice/product_composition_registry.py |
| `FormalLiveVoiceViolation` | exception | 4 | 0 | 20 |  |

### `server/live_voice/jiuwenswarm_agent_adapter.py`（106 行；被 1 个生产文件导入；2 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `JiuWenSwarmAgentAdapter` | owner | 66 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `_tool_result_succeeded` | function | 20 | 0 | 1 |  |

### `server/live_voice/agent_bridge.py`（105 行；被 3 个生产文件导入；5 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `AgentBridgePort` | owner | 56 | 0 | 0 |  |
| `AgentEvent` | value | 12 | 3 | 4 | server/live_voice/agent_bridge_runtime.py, server/live_voice/agent_conversation_runtime.py, server/live_voice/jiuwenswarm_agent_adapter.py |
| `AgentRequest` | value | 7 | 0 | 3 |  |
| `AgentBridgeViolation` | exception | 4 | 0 | 3 |  |
| `AgentHandler` | value | 2 | 0 | 2 |  |

### `server/runtime/agent_adapter/formal_tool_gate.py`（75 行；被 2 个生产文件导入；9 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `request_pause` | function | 9 | 1 | 2 | server/runtime/agent_adapter/interface.py |
| `release` | function | 6 | 2 | 4 | server/runtime/agent_adapter/interface.py, server/runtime/agent_adapter/interface_deep.py |
| `abort` | function | 6 | 2 | 4 | server/runtime/agent_adapter/interface.py, server/runtime/agent_adapter/interface_deep.py |
| `should_pause` | function | 5 | 1 | 2 | server/runtime/agent_adapter/interface_deep.py |
| `_require_session` | function | 4 | 0 | 3 |  |
| `snapshot` | function | 3 | 2 | 1 | server/runtime/agent_adapter/interface.py, server/runtime/agent_adapter/interface_deep.py |
| `_MAX_ENTRIES` | constant | 1 | 0 | 1 |  |
| `_PAUSED` | constant | 1 | 0 | 4 |  |
| `_RELEASED` | constant | 1 | 0 | 0 |  |

## 07 Task domain/control（4 文件，5,342 行）

### `server/live_voice/formal_task_models.py`（2,628 行；被 23 个生产文件导入；53 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ResolvedTaskContext` | value | 233 | 6 | 5 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_confirmation.py, server/live_voice/p3_production_intent_composition.py |
| `FormalTaskSpec` | value | 192 | 5 | 5 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py |
| `ExecutorObservation` | value | 180 | 3 | 3 | server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `TaskEventConsumerAuthorityPage` | value | 139 | 2 | 1 | server/live_voice/task_progress_return.py, server/live_voice/task_store.py |
| `TaskAuthorizationGrant` | value | 134 | 8 | 1 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/presentation_ledger.py |
| `TaskEventAuthoritySnapshot` | value | 120 | 2 | 1 | server/live_voice/task_event_subscription.py, server/live_voice/task_store.py |
| `PersistentTaskEvent` | value | 117 | 9 | 15 | server/live_voice/observability.py, server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py |
| `PersistentAdmissionRecord` | value | 104 | 3 | 2 | server/live_voice/p3_production_intent_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/task_store.py |
| `TaskUnreadPage` | value | 92 | 3 | 1 | server/live_voice/p3_authenticated_composition.py, server/live_voice/presentation_ledger.py, server/live_voice/task_store.py |
| `PersistedExecutorSelection` | value | 91 | 4 | 4 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py |
| `TaskEventConsumerCursorBaseline` | value | 88 | 3 | 3 | server/live_voice/progress_notification_arbiter.py, server/live_voice/task_progress_return.py, server/live_voice/task_store.py |
| `PersistentTaskRecord` | value | 86 | 8 | 7 | server/live_voice/observability.py, server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_production_intent_composition.py |
| `TaskResultRecord` | value | 69 | 5 | 1 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/presentation_ledger.py |
| `TaskMutationPrecondition` | value | 64 | 3 | 2 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/task_store.py |
| `TaskRetryPrecondition` | value | 59 | 3 | 4 | server/live_voice/p3_authenticated_composition.py, server/live_voice/task_store.py, server/live_voice/voice_task_policy.py |
| `TaskAdjustmentRequest` | value | 55 | 2 | 3 | server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `TaskRetryProductRequestFingerprint` | value | 49 | 4 | 2 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/task_store.py |
| `AdmissionPolicy` | value | 48 | 3 | 1 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/task_store.py |
| `PersistentAttemptRecord` | value | 43 | 5 | 9 | server/live_voice/p3_production_intent_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py |
| `TaskMutationResult` | value | 35 | 2 | 1 | server/live_voice/persistent_task_core.py, server/live_voice/task_store.py |
| `TaskResultArtifact` | value | 34 | 3 | 5 | server/live_voice/product_composition_registry.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `TaskAdjustmentDeliveryResult` | value | 34 | 3 | 1 | server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `PersistentOutboxItem` | value | 33 | 4 | 1 | server/live_voice/observability.py, server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py |
| `ExecutorRetryReadiness` | value | 30 | 2 | 1 | server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py |
| `AppliedTaskRetryReplay` | value | 28 | 2 | 1 | server/live_voice/persistent_task_core.py, server/live_voice/task_store.py |
| `command_result_extensions` | function | 27 | 2 | 1 | server/live_voice/persistent_task_core.py, server/live_voice/task_store.py |
| `DurableRecoveryAuthoritySnapshot` | value | 26 | 1 | 1 | server/live_voice/task_store.py |
| `TaskRetryAuthoritySnapshot` | value | 23 | 2 | 1 | server/live_voice/persistent_task_core.py, server/live_voice/task_store.py |
| `_parse_utc` | function | 22 | 4 | 12 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_confirmation.py, server/live_voice/product_authority.py |
| `TaskAdjustmentSettlement` | value | 20 | 3 | 1 | server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `ExecutorDeliveryResult` | value | 17 | 2 | 1 | server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py |
| `require_exact_payload` | function | 16 | 1 | 1 | server/live_voice/persistent_task_core.py |
| `_utf8_size` | function | 9 | 0 | 10 |  |
| `safe_json_value` | function | 9 | 0 | 3 |  |
| `TaskCommandDisposition` | value | 8 | 2 | 3 | server/live_voice/persistent_task_core.py, server/live_voice/task_store.py |
| `canonical_task_adjustment_rejection_reason` | function | 8 | 1 | 2 | server/live_voice/persistent_task_core.py |
| `_require_text` | function | 8 | 2 | 57 | server/live_voice/presentation_ledger.py, server/live_voice/product_authority.py |
| `FormalTaskState` | value | 6 | 5 | 10 | server/live_voice/p3_production_intent_composition.py, server/live_voice/product_composition_registry.py, server/live_voice/project_code_executor.py |
| `FormalTaskViolation` | exception | 5 | 19 | 151 | server/live_voice/executor_capabilities.py, server/live_voice/native_agent_model.py, server/live_voice/p2_response_generation_store.py |
| `OutboxState` | value | 5 | 2 | 2 | server/live_voice/observability.py, server/live_voice/task_store.py |

### `server/live_voice/persistent_task_core.py`（1,627 行；被 1 个生产文件导入；12 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `PersistentTaskCore` | owner | 1354 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `FormalExecutor` | value | 62 | 0 | 2 |  |
| `project_task_event` | function | 51 | 0 | 1 |  |
| `_failure` | function | 38 | 0 | 2 |  |
| `_AdjustmentDeliveryOwner` | value | 12 | 0 | 6 |  |
| `_PROJECTABLE_TASK_EVENTS` | constant | 10 | 0 | 1 |  |
| `_contract_error` | function | 8 | 0 | 1 |  |
| `ReconciliationEventSink` | constant | 3 | 1 | 2 | server/live_voice/p3_authenticated_composition.py |
| `_OUTBOX_CLAIM_LEASE` | constant | 1 | 0 | 2 |  |
| `_ADJUSTMENT_CLAIM_RENEW_SECONDS` | constant | 1 | 0 | 1 |  |
| `_MAX_INFLIGHT_ADJUSTMENTS` | constant | 1 | 0 | 1 |  |
| `_ADJUSTMENT_CLEANUP_SECONDS` | constant | 1 | 0 | 3 |  |

### `server/live_voice/task_core.py`（714 行；被 3 个生产文件导入；17 个顶层 symbol，其中 2 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `TaskCore` | owner | 500 | 0 | 0 |  |
| `TaskCommand` | value | 30 | 1 | 5 | server/live_voice/voice_task_bridge.py |
| `TaskSpec` | value | 28 | 1 | 3 | server/live_voice/voice_task_bridge.py |
| `TaskEvent` | value | 10 | 0 | 11 |  |
| `TaskRecord` | value | 9 | 0 | 6 |  |
| `TaskCommandResult` | value | 9 | 0 | 9 |  |
| `project_work_progress` | function | 8 | 0 | 0 |  |
| `TaskCoreSnapshot` | value | 7 | 0 | 2 |  |
| `TaskState` | value | 6 | 2 | 15 | server/live_voice/p3_production_intent_composition.py, server/live_voice/production_task_intent.py |
| `TaskQuery` | value | 6 | 0 | 1 |  |
| `AttemptRecord` | value | 6 | 0 | 4 |  |
| `WorkProgress` | value | 6 | 0 | 2 |  |
| `DispatchIntent` | value | 6 | 0 | 4 |  |
| `TaskCoreViolation` | exception | 5 | 0 | 19 |  |
| `CancelIntent` | value | 5 | 0 | 3 |  |
| `AttemptState` | value | 4 | 2 | 8 | server/live_voice/p3_production_intent_composition.py, server/live_voice/production_task_intent.py |
| `AuthorizationContext` | value | 4 | 0 | 7 |  |

### `server/live_voice/executor_capabilities.py`（373 行；被 4 个生产文件导入；21 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ExecutorCapabilityProfile` | value | 89 | 4 | 9 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_production_intent_composition.py, server/live_voice/project_code_executor.py |
| `TaskExecutionRequirements` | value | 54 | 2 | 9 | server/live_voice/p3_authenticated_composition.py, server/live_voice/project_code_executor.py |
| `ExecutorSelection` | value | 38 | 2 | 4 | server/live_voice/p3_authenticated_composition.py, server/live_voice/project_code_executor.py |
| `select_executor` | function | 34 | 2 | 1 | server/live_voice/p3_authenticated_composition.py, server/live_voice/project_code_executor.py |
| `_operation_versions` | function | 21 | 0 | 2 |  |
| `_compatible` | function | 19 | 0 | 2 |  |
| `_PROFILE_FIELDS` | constant | 13 | 0 | 1 |  |
| `_REQUIREMENT_FIELDS` | constant | 8 | 0 | 1 |  |
| `_enforcement_facts` | function | 7 | 0 | 1 |  |
| `_identifier` | function | 6 | 0 | 9 |  |
| `_decoded_operation_versions` | function | 6 | 0 | 2 |  |
| `_SENSITIVE_IDENTIFIER` | constant | 4 | 0 | 1 |  |
| `EXECUTOR_CAPABILITY_PROFILE_SCHEMA_VERSION` | constant | 3 | 1 | 2 | server/live_voice/project_code_executor.py |
| `TASK_EXECUTION_REQUIREMENTS_SCHEMA_VERSION` | constant | 3 | 1 | 2 | server/live_voice/p3_authenticated_composition.py |
| `_SIDE_EFFECT_FACTS` | constant | 3 | 0 | 1 |  |
| `PROJECT_MUTATION_SIDE_EFFECT_FACT` | constant | 1 | 0 | 2 |  |
| `_SAFE_IDENTIFIER` | constant | 1 | 0 | 1 |  |
| `_VERSION` | constant | 1 | 0 | 1 |  |
| `_SHA256` | constant | 1 | 0 | 1 |  |
| `_SELECTION_FIELDS` | constant | 1 | 0 | 1 |  |
| `_DURABILITY_RANK` | constant | 1 | 0 | 4 |  |

## 08 Task Store（1 文件，15,190 行）

### `server/live_voice/task_store.py`（15,190 行；被 10 个生产文件导入；61 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SqliteTaskStore` | owner | 14093 | 5 | 1 | server/live_voice/p3_authenticated_composition.py, server/live_voice/p3_production_intent_composition.py, server/live_voice/persistent_task_core.py |
| `_TASK_STORE_COLUMNS` | constant | 157 | 0 | 11 |  |
| `_OUTBOX_BINDING_SELECT` | constant | 131 | 0 | 5 |  |
| `_TASK_STORE_NOT_NULL` | constant | 86 | 0 | 2 |  |
| `_selection_from_attempt_row` | function | 56 | 0 | 16 |  |
| `_TASK_STORE_FOREIGN_KEYS_V6` | constant | 31 | 0 | 1 |  |
| `_TASK_STORE_PRIMARY_KEYS` | constant | 30 | 0 | 2 |  |
| `_TASK_STORE_FOREIGN_KEYS_V3` | constant | 29 | 0 | 2 |  |
| `_canonical_utc_order_key` | function | 25 | 0 | 8 |  |
| `_selection_from_fingerprint_payload` | function | 24 | 0 | 5 |  |
| `_TASK_STORE_INTEGER_COLUMNS` | constant | 21 | 0 | 1 |  |
| `_stored_record` | function | 19 | 0 | 17 |  |
| `_RETRY_BUSINESS_DECISIONS` | constant | 18 | 0 | 5 |  |
| `_TASK_STORE_NAMED_INDEXES_V5` | constant | 18 | 0 | 2 |  |
| `_utc_datetime` | function | 16 | 0 | 18 |  |
| `TaskDurabilityDiagnosticSnapshot` | value | 15 | 2 | 2 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py |
| `_TASK_STORE_UNIQUE_KEYS_V5` | constant | 15 | 0 | 2 |  |
| `_CONTROL_BUSINESS_DECISIONS` | constant | 14 | 0 | 2 |  |
| `_CANCEL_BUSINESS_DECISIONS` | constant | 14 | 0 | 3 |  |
| `_task_binding_from_row` | function | 13 | 0 | 6 |  |
| `_TASK_STORE_UNIQUE_KEYS_V6` | constant | 12 | 0 | 1 |  |
| `_TASK_STORE_TABLES_V2` | constant | 11 | 0 | 2 |  |
| `_TASK_STORE_NAMED_INDEXES_V6` | constant | 11 | 0 | 1 |  |
| `_TASK_STORE_UNIQUE_KEYS_V3` | constant | 11 | 0 | 3 |  |
| `_utc_plus_seconds` | function | 11 | 0 | 2 |  |
| `TaskOutboxDiagnosticFact` | value | 10 | 0 | 2 |  |
| `_SUCCESSOR_BUSINESS_DECISIONS` | constant | 10 | 0 | 2 |  |
| `_ADJUST_BUSINESS_DECISIONS` | constant | 10 | 0 | 2 |  |
| `_ACK_BUSINESS_DECISIONS` | constant | 10 | 0 | 2 |  |
| `_TASK_EVENT_CONSUMPTION_FOREIGN_KEYS` | constant | 10 | 0 | 1 |  |
| `_selection_fingerprint_payload` | function | 10 | 0 | 3 |  |
| `_TASK_STORE_TABLES` | constant | 9 | 0 | 3 |  |
| `_TASK_STORE_BLOB_COLUMNS` | constant | 9 | 0 | 1 |  |
| `_TASK_STORE_NAMED_INDEXES_V3` | constant | 9 | 0 | 2 |  |
| `_json_load` | function | 9 | 0 | 56 |  |
| `_TASK_STORE_DEFAULTS` | constant | 8 | 0 | 1 |  |
| `_UPDATE_BUSINESS_DECISIONS` | constant | 6 | 0 | 2 |  |
| `_LEGACY_CANDIDATE_V6_RECOVERY_FENCE_SQL` | constant | 6 | 0 | 1 |  |
| `_LEGACY_CANDIDATE_V6_RECOVERY_FENCE_INDEXES` | constant | 6 | 0 | 2 |  |
| `_CANONICAL_UTC_RE` | constant | 5 | 0 | 1 |  |

## 09 Project executor（1 文件，6,881 行）

### `server/live_voice/project_code_executor.py`（6,881 行；被 1 个生产文件导入；93 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `DirectProjectCodeExecutorAdapter` | owner | 3438 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `_DirectProjectAttemptJournal` | owner | 1129 | 0 | 2 |  |
| `ProjectCodeExecutorAdapter` | owner | 492 | 0 | 1 |  |
| `ProjectExecutionBinding` | value | 147 | 1 | 6 | server/live_voice/p3_authenticated_composition.py |
| `DirectProjectManagedBaselineReader` | class | 134 | 1 | 1 | server/live_voice/p3_authenticated_composition.py |
| `_AttemptOwnershipLock` | owner | 86 | 0 | 9 |  |
| `_create_attempt_worktree` | function | 62 | 0 | 1 |  |
| `_decode_d2_checkpoint_state` | function | 57 | 0 | 4 |  |
| `_closed_direct_stream_observation` | function | 53 | 0 | 1 |  |
| `_project_tree_fingerprint` | function | 48 | 0 | 8 |  |
| `_remove_attempt_worktree` | function | 46 | 0 | 2 |  |
| `_reject_git_visible_symlinks` | function | 43 | 0 | 5 |  |
| `_git_visible_patch` | function | 39 | 0 | 2 |  |
| `_path_fingerprint` | function | 37 | 0 | 1 |  |
| `_attempt_result_artifacts` | function | 37 | 0 | 1 |  |
| `_attempt_patch` | function | 34 | 0 | 1 |  |
| `_LEGACY_DIRECT_D2_CAPABILITY_PROFILE` | constant | 31 | 0 | 3 |  |
| `_project_content_fingerprint` | function | 31 | 0 | 8 |  |
| `_runtime_support_governance` | function | 30 | 0 | 2 |  |
| `_seed_attempt_worktree` | function | 29 | 0 | 1 |  |
| `_relocate_result_artifact_paths` | function | 29 | 0 | 1 |  |
| `_applied_result_artifacts` | function | 28 | 0 | 6 |  |
| `_DirectAttempt` | value | 27 | 0 | 18 |  |
| `_decode_result_artifacts` | function | 26 | 0 | 2 |  |
| `_LEGACY_DIRECT_D0_CAPABILITY_PROFILE` | constant | 25 | 0 | 3 |  |
| `_d2_checkpoint_state` | function | 23 | 0 | 1 |  |
| `_applied_checkpoint_state` | function | 23 | 0 | 1 |  |
| `_applied_artifacts_match` | function | 21 | 0 | 0 |  |
| `_apply_attempt_patch` | function | 20 | 0 | 2 |  |
| `_worktree_registered` | function | 17 | 0 | 4 |  |
| `_git_output` | function | 16 | 0 | 15 |  |
| `_closed_tool_result_status` | function | 15 | 0 | 1 |  |
| `DirectStreamObservation` | value | 14 | 0 | 4 |  |
| `_expected_project_state_matches` | function | 14 | 0 | 8 |  |
| `_git_root` | function | 13 | 0 | 2 |  |
| `_is_unsafe_filesystem_link` | function | 13 | 0 | 9 |  |
| `_bounded_chat_final` | function | 13 | 0 | 3 |  |
| `_require_attempt_target_unchanged` | function | 13 | 0 | 2 |  |
| `LegacyProjectTaskService` | value | 12 | 0 | 2 |  |
| `_attempt_ownership_lock_path` | function | 12 | 0 | 1 |  |

## 10 Checkpoint/effect（6 文件，2,953 行）

### `server/live_voice/durability_effects.py`（920 行；被 3 个生产文件导入；33 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ExternalEffectBinding` | value | 82 | 2 | 26 | server/live_voice/durability_readers.py, server/live_voice/project_code_executor.py |
| `ExternalEffectObservation` | value | 79 | 3 | 9 | server/live_voice/durability_readers.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `EffectContinuationAuthorization` | value | 77 | 3 | 5 | server/live_voice/durability_readers.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `ExternalEffectSettlement` | value | 77 | 3 | 5 | server/live_voice/durability_readers.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `decide_effect_reconciliation` | function | 76 | 0 | 1 |  |
| `EffectDispatchReceipt` | value | 75 | 2 | 8 | server/live_voice/durability_readers.py, server/live_voice/project_code_executor.py |
| `effect_fact_from_bytes` | function | 62 | 1 | 1 | server/live_voice/durability_readers.py |
| `ExternalEffectDispatch` | value | 56 | 3 | 5 | server/live_voice/durability_readers.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `ExternalEffectIntent` | value | 32 | 2 | 8 | server/live_voice/durability_readers.py, server/live_voice/project_code_executor.py |
| `_text` | function | 19 | 2 | 23 | server/live_voice/durability_readers.py, server/live_voice/project_code_executor.py |
| `_scope` | function | 19 | 1 | 1 | server/live_voice/durability_readers.py |
| `_AuthorityFreeEffectFact` | owner | 18 | 0 | 8 |  |
| `_fact_kind` | function | 17 | 0 | 1 |  |
| `_profile` | function | 13 | 1 | 1 | server/live_voice/durability_readers.py |
| `_reject_duplicate_keys` | function | 12 | 0 | 1 |  |
| `effect_fact_bytes` | function | 11 | 2 | 2 | server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `EffectReconciliationDecision` | value | 11 | 0 | 3 |  |
| `EffectFact` | constant | 8 | 2 | 4 | server/live_voice/durability_readers.py, server/live_voice/task_store.py |
| `_FACT_TYPES` | constant | 8 | 0 | 2 |  |
| `_positive` | function | 7 | 0 | 16 |  |
| `_nonnegative` | function | 7 | 0 | 12 |  |
| `_digest` | function | 7 | 1 | 15 | server/live_voice/durability_readers.py |
| `_strict` | function | 7 | 0 | 8 |  |
| `EffectReconciliationKind` | value | 6 | 0 | 8 |  |
| `ExternalEffectContractViolation` | exception | 4 | 0 | 49 |  |
| `EffectObservationKind` | value | 4 | 1 | 6 | server/live_voice/project_code_executor.py |
| `EffectSettlementKind` | value | 4 | 1 | 4 | server/live_voice/project_code_executor.py |
| `_sha256` | function | 2 | 1 | 2 | server/live_voice/durability_readers.py |
| `EXTERNAL_EFFECT_FACT_CONTRACT_VERSION` | constant | 1 | 0 | 3 |  |
| `MAX_EXTERNAL_EFFECT_FACT_BYTES` | constant | 1 | 0 | 2 |  |
| `_MAX_TEXT_BYTES` | constant | 1 | 1 | 1 | server/live_voice/durability_readers.py |
| `_MAX_OBSERVATIONS` | constant | 1 | 0 | 1 |  |
| `_SHA256` | constant | 1 | 1 | 1 | server/live_voice/durability_readers.py |

### `server/live_voice/durability_readers.py`（689 行；被 2 个生产文件导入；25 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `verify_effect_prefix` | function | 238 | 1 | 1 | server/live_voice/task_store.py |
| `_bounded_unique_rows` | function | 93 | 0 | 2 |  |
| `verify_checkpoint_prefix` | function | 68 | 1 | 1 | server/live_voice/task_store.py |
| `DurabilityReadBinding` | value | 26 | 2 | 13 | server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `_prefix_digest` | function | 21 | 0 | 2 |  |
| `_text` | function | 19 | 1 | 6 | server/live_voice/project_code_executor.py |
| `_scope` | function | 19 | 0 | 2 |  |
| `_AuthorityFreePrefix` | owner | 18 | 0 | 2 |  |
| `_normalize_binding` | function | 18 | 0 | 3 |  |
| `_profile` | function | 13 | 0 | 2 |  |
| `_check_expected_prefix` | function | 13 | 0 | 2 |  |
| `_digest` | function | 7 | 0 | 1 |  |
| `CheckpointPrefixRow` | value | 5 | 1 | 5 | server/live_voice/task_store.py |
| `EffectPrefixRow` | value | 5 | 1 | 5 | server/live_voice/task_store.py |
| `VerifiedCheckpointPrefix` | value | 5 | 2 | 3 | server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `VerifiedEffectPrefix` | value | 5 | 2 | 3 | server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `DurabilityPrefixViolation` | exception | 4 | 1 | 47 | server/live_voice/task_store.py |
| `_sha256` | function | 2 | 0 | 2 |  |
| `DURABILITY_PREFIX_CONTRACT_VERSION` | constant | 1 | 0 | 2 |  |
| `MAX_DURABILITY_PREFIX_ROWS` | constant | 1 | 0 | 3 |  |
| `MAX_DURABILITY_PREFIX_ITEM_BYTES` | constant | 1 | 0 | 2 |  |
| `MAX_DURABILITY_PREFIX_BYTES` | constant | 1 | 0 | 2 |  |
| `_MAX_TEXT_BYTES` | constant | 1 | 0 | 1 |  |
| `_SHA256` | constant | 1 | 0 | 2 |  |
| `PrefixRow` | constant | 1 | 0 | 3 |  |

### `server/live_voice/durability_checkpoint.py`（499 行；被 3 个生产文件导入；16 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `D1Checkpoint` | value | 322 | 3 | 4 | server/live_voice/durability_readers.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `_text` | function | 19 | 2 | 16 | server/live_voice/durability_readers.py, server/live_voice/project_code_executor.py |
| `_scope` | function | 19 | 1 | 2 | server/live_voice/durability_readers.py |
| `_decode_base64` | function | 19 | 0 | 1 |  |
| `_profile` | function | 13 | 1 | 2 | server/live_voice/durability_readers.py |
| `_reject_duplicate_keys` | function | 12 | 0 | 1 |  |
| `_positive` | function | 7 | 0 | 3 |  |
| `_nonnegative` | function | 7 | 0 | 9 |  |
| `_digest` | function | 7 | 1 | 16 | server/live_voice/durability_readers.py |
| `DurabilityCheckpointViolation` | exception | 4 | 0 | 32 |  |
| `_sha256` | function | 2 | 1 | 4 | server/live_voice/durability_readers.py |
| `D1_CHECKPOINT_CONTRACT_VERSION` | constant | 1 | 0 | 4 |  |
| `MAX_D1_CHECKPOINT_STATE_BYTES` | constant | 1 | 0 | 3 |  |
| `MAX_D1_CHECKPOINT_WIRE_BYTES` | constant | 1 | 1 | 2 | server/live_voice/durability_readers.py |
| `_MAX_TEXT_BYTES` | constant | 1 | 1 | 1 | server/live_voice/durability_readers.py |
| `_SHA256` | constant | 1 | 1 | 1 | server/live_voice/durability_readers.py |

### `server/live_voice/durability_recovery_facts.py`（466 行；被 3 个生产文件导入；15 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ExecutorRecoveryFacts` | value | 285 | 3 | 4 | server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `_timestamp_key` | function | 30 | 0 | 6 |  |
| `_text` | function | 19 | 1 | 17 | server/live_voice/project_code_executor.py |
| `_scope` | function | 19 | 0 | 2 |  |
| `_profile` | function | 13 | 0 | 2 |  |
| `_reject_duplicate_keys` | function | 12 | 0 | 1 |  |
| `_nonnegative` | function | 7 | 0 | 6 |  |
| `_digest` | function | 7 | 0 | 5 |  |
| `ExecutorRecoveryFactsViolation` | exception | 4 | 0 | 29 |  |
| `_UTC_TIMESTAMP` | constant | 3 | 0 | 1 |  |
| `_sha256` | function | 2 | 0 | 2 |  |
| `EXECUTOR_RECOVERY_FACTS_VERSION` | constant | 1 | 0 | 4 |  |
| `MAX_EXECUTOR_RECOVERY_FACTS_BYTES` | constant | 1 | 0 | 2 |  |
| `_MAX_TEXT_BYTES` | constant | 1 | 0 | 1 |  |
| `_SHA256` | constant | 1 | 0 | 1 |  |

### `server/live_voice/durability_authority.py`（229 行；被 3 个生产文件导入；11 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `_mint_durability_mutation_authorization` | function | 74 | 1 | 0 | server/live_voice/project_code_executor.py |
| `DurabilityMutationAuthorization` | value | 67 | 3 | 6 | server/live_voice/persistent_task_core.py, server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `_receipt_payload` | function | 23 | 0 | 2 |  |
| `_OPERATIONS` | constant | 9 | 0 | 1 |  |
| `_text` | function | 4 | 1 | 6 | server/live_voice/project_code_executor.py |
| `_RECEIPT_REGISTRY` | constant | 3 | 0 | 2 |  |
| `_durability_authorization_payload_digest` | function | 2 | 2 | 0 | server/live_voice/project_code_executor.py, server/live_voice/task_store.py |
| `_CONSTRUCTION_TOKEN` | constant | 1 | 0 | 3 |  |
| `_RECEIPT_SIGNING_KEY` | constant | 1 | 0 | 2 |  |
| `_RECEIPT_REGISTRY_LOCK` | constant | 1 | 0 | 2 |  |
| `_SHA256` | constant | 1 | 0 | 4 |  |

### `server/live_voice/durability_identity.py`（150 行；被 8 个生产文件导入；8 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `DurabilityProfileBinding` | value | 84 | 8 | 2 | server/live_voice/durability_authority.py, server/live_voice/durability_checkpoint.py, server/live_voice/durability_effects.py |
| `_text` | function | 19 | 6 | 12 | server/live_voice/durability_authority.py, server/live_voice/durability_checkpoint.py, server/live_voice/durability_effects.py |
| `_digest` | function | 7 | 4 | 2 | server/live_voice/durability_checkpoint.py, server/live_voice/durability_effects.py, server/live_voice/durability_readers.py |
| `DurabilityIdentityViolation` | exception | 4 | 4 | 8 | server/live_voice/durability_checkpoint.py, server/live_voice/durability_effects.py, server/live_voice/durability_readers.py |
| `DURABILITY_PROFILE_BINDING_VERSION` | constant | 1 | 0 | 3 |  |
| `_MAX_DURABILITY_TEXT_BYTES` | constant | 1 | 0 | 1 |  |
| `_SHA256` | constant | 1 | 5 | 1 | server/live_voice/durability_authority.py, server/live_voice/durability_checkpoint.py, server/live_voice/durability_effects.py |
| `_DURABILITY_LEVELS` | constant | 1 | 0 | 1 |  |

## 11 Task event/progress（5 文件，8,164 行）

### `server/live_voice/task_progress_return.py`（2,291 行；被 6 个生产文件导入；40 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `TaskProgressReturnBridge` | owner | 1117 | 1 | 2 | server/live_voice/product_p3_text_adapter.py |
| `_ConsumerTaskEventSubscription` | class | 333 | 0 | 3 |  |
| `_project_task_progress_event` | function | 187 | 0 | 2 |  |
| `TaskEventAuthorityProgressSource` | owner | 148 | 1 | 5 | server/live_voice/p3_authenticated_composition.py |
| `_canonical_binding` | function | 53 | 0 | 2 |  |
| `TaskProgressReturnSnapshot` | value | 25 | 0 | 4 |  |
| `TaskProgressReturnReason` | value | 23 | 1 | 90 | server/live_voice/product_p3_text_adapter.py |
| `_evidence_id` | function | 20 | 0 | 13 |  |
| `TaskProgressReturnLease` | owner | 18 | 2 | 4 | server/live_voice/product_composition_registry.py, server/live_voice/product_p3_text_adapter.py |
| `TASK_PROGRESS_NON_PRESENTABLE_EVENTS` | constant | 17 | 1 | 2 | server/live_voice/presentation_ledger.py |
| `TaskProgressOriginBinding` | value | 16 | 3 | 19 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py, server/live_voice/product_p3_text_adapter.py |
| `_authorization_fingerprint` | function | 14 | 0 | 7 |  |
| `TaskProgressSourceDecision` | value | 13 | 0 | 28 |  |
| `PreparedTaskProgressSource` | value | 12 | 1 | 3 | server/live_voice/product_p3_text_adapter.py |
| `_TASK_EVENT_PRODUCERS` | constant | 11 | 0 | 1 |  |
| `task_progress_presentation_allowed` | function | 11 | 2 | 0 | server/live_voice/presentation_ledger.py, server/live_voice/product_composition_registry.py |
| `TaskProgressHandoffKind` | value | 11 | 0 | 10 |  |
| `TaskProgressNotificationIntent` | value | 9 | 4 | 4 | server/live_voice/agent_conversation_runtime.py, server/live_voice/product_composition_registry.py, server/live_voice/product_p2_interaction_adapter.py |
| `TaskProgressReturnState` | value | 8 | 1 | 53 | server/live_voice/product_composition_registry.py |
| `TaskProgressTextEvent` | value | 8 | 2 | 3 | server/live_voice/product_composition_registry.py, server/live_voice/product_p3_text_adapter.py |
| `_required_text` | function | 8 | 2 | 1 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py |
| `_stable_consumer_scope_matches` | function | 8 | 0 | 3 |  |
| `TASK_PROGRESS_PRESENTABLE_EVENTS` | constant | 7 | 1 | 3 | server/live_voice/presentation_ledger.py |
| `project_task_progress_event` | function | 7 | 0 | 1 |  |
| `TaskProgressReturnActivation` | value | 7 | 1 | 6 | server/live_voice/product_p3_text_adapter.py |
| `DeferredVoiceOwnership` | value | 6 | 2 | 4 | server/live_voice/product_composition_registry.py, server/live_voice/product_p3_text_adapter.py |
| `TaskProgressReturnViolation` | exception | 5 | 0 | 6 |  |
| `TaskProgressProjection` | value | 5 | 0 | 8 |  |
| `_violation` | function | 4 | 1 | 23 | server/live_voice/product_p2_interaction_adapter.py |
| `TaskProgressOriginKind` | value | 3 | 4 | 15 | server/live_voice/agent_conversation_runtime.py, server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py |
| `_EVENTS_CAPABILITY` | constant | 1 | 0 | 2 |  |
| `_QUIET_LIFECYCLE_EVENTS` | constant | 1 | 0 | 2 |  |
| `_PROJECTABLE_EVENTS` | constant | 1 | 0 | 2 |  |
| `_NO_PROJECTION_EVENTS` | constant | 1 | 0 | 1 |  |
| `_SOURCE_EXTENSION` | constant | 1 | 0 | 3 |  |
| `_PROGRESS_EVENT_PREFIX` | constant | 1 | 0 | 2 |  |
| `GenerationIsCurrent` | constant | 1 | 1 | 2 | server/live_voice/product_p3_text_adapter.py |
| `ForegroundSupplier` | constant | 1 | 1 | 2 | server/live_voice/product_p3_text_adapter.py |
| `VoiceIntentSink` | constant | 1 | 1 | 3 | server/live_voice/product_p3_text_adapter.py |
| `TextEventSink` | constant | 1 | 1 | 2 | server/live_voice/product_p3_text_adapter.py |

### `server/live_voice/progress_notification_arbiter.py`（2,228 行；被 3 个生产文件导入；36 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProgressNotificationArbiter` | owner | 1772 | 3 | 1 | server/live_voice/product_composition_registry.py, server/live_voice/product_p3_text_adapter.py, server/live_voice/task_progress_return.py |
| `_attempt_epoch_number` | function | 46 | 1 | 2 | server/live_voice/task_progress_return.py |
| `_VerifiedConsumerProjection` | value | 25 | 0 | 3 |  |
| `_VerifiedNoProjectionAdvance` | value | 24 | 0 | 4 |  |
| `_VerifiedAttemptEpochBaseline` | value | 22 | 0 | 3 |  |
| `_mint_verified_no_projection_advance` | function | 20 | 1 | 0 | server/live_voice/task_progress_return.py |
| `_VerifiedConsumerCursorBaseline` | value | 19 | 0 | 4 |  |
| `_mint_verified_attempt_epoch_baseline` | function | 18 | 1 | 0 | server/live_voice/task_progress_return.py |
| `ProgressNotificationArbiterSnapshot` | value | 17 | 0 | 4 |  |
| `NotificationDecision` | value | 14 | 1 | 17 | server/live_voice/task_progress_return.py |
| `_mint_verified_consumer_projection` | function | 13 | 1 | 0 | server/live_voice/task_progress_return.py |
| `ForegroundSnapshot` | value | 11 | 2 | 6 | server/live_voice/product_composition_registry.py, server/live_voice/task_progress_return.py |
| `ProgressNotificationBinding` | value | 11 | 1 | 22 | server/live_voice/task_progress_return.py |
| `_NO_PROJECTION_EVENT_TYPES` | constant | 11 | 0 | 1 |  |
| `_mint_verified_consumer_cursor_baseline` | function | 9 | 1 | 0 | server/live_voice/task_progress_return.py |
| `_stable_consumer_scope_matches` | function | 8 | 1 | 6 | server/live_voice/task_progress_return.py |
| `NotificationDisposition` | value | 7 | 1 | 11 | server/live_voice/task_progress_return.py |
| `NoProjectionAdvanceDisposition` | value | 6 | 1 | 16 | server/live_voice/task_progress_return.py |
| `NoProjectionAdvanceDecision` | value | 6 | 0 | 17 |  |
| `ProgressNotificationArbiterViolation` | exception | 5 | 0 | 19 |  |
| `_InputRejected` | exception | 5 | 0 | 37 |  |
| `ForegroundFact` | value | 4 | 1 | 6 | server/live_voice/product_composition_registry.py |
| `SpeechPolicy` | value | 4 | 1 | 5 | server/live_voice/product_composition_registry.py |
| `_WorkState` | value | 4 | 0 | 7 |  |
| `_PendingNotification` | value | 4 | 0 | 2 |  |
| `SpeechDisposition` | value | 3 | 0 | 12 |  |
| `_SequenceState` | value | 3 | 0 | 19 |  |
| `_NO_PROJECTION_ADVANCE_TOKEN` | constant | 1 | 0 | 2 |  |
| `_ATTEMPT_EPOCH_BASELINE_TOKEN` | constant | 1 | 0 | 2 |  |
| `_CONSUMER_CURSOR_BASELINE_TOKEN` | constant | 1 | 0 | 2 |  |
| `_CONSUMER_PROJECTION_TOKEN` | constant | 1 | 0 | 2 |  |
| `_NO_PROJECTION_SOURCE_DOMAIN` | constant | 1 | 0 | 1 |  |
| `_NO_PROJECTION_PROGRESS_DOMAIN` | constant | 1 | 0 | 1 |  |
| `_NO_PROJECTION_WORK_DOMAIN` | constant | 1 | 0 | 1 |  |
| `_NO_PROJECTION_OBSERVATION_DOMAIN` | constant | 1 | 0 | 1 |  |
| `_TASK_PROGRESS_RETURN_EXTENSION` | constant | 1 | 0 | 2 |  |

### `server/live_voice/task_event_subscription.py`（1,568 行；被 3 个生产文件导入；13 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `TaskEventSubscription` | class | 1395 | 3 | 2 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_p3_text_adapter.py, server/live_voice/task_progress_return.py |
| `TaskEventSubscriptionSnapshot` | value | 24 | 1 | 3 | server/live_voice/task_progress_return.py |
| `_TASK_EVENT_PRODUCERS` | constant | 19 | 1 | 3 | server/live_voice/task_progress_return.py |
| `TaskEventSource` | value | 15 | 0 | 3 |  |
| `_ATTEMPT_TRANSITIONS` | constant | 11 | 0 | 1 |  |
| `_TASK_LIFECYCLE_EVENT_STATES` | constant | 9 | 0 | 1 |  |
| `TaskEventSubscriptionState` | value | 8 | 1 | 45 | server/live_voice/task_progress_return.py |
| `TaskEventAuthoritySource` | value | 6 | 0 | 1 |  |
| `_ATTEMPT_LIFECYCLE_EVENT_STATES` | constant | 5 | 0 | 2 |  |
| `_INTERNAL_ATTEMPT_TERMINAL_PRODUCERS` | constant | 3 | 0 | 1 |  |
| `_CANONICAL_EVENT_TYPES` | constant | 3 | 0 | 1 |  |
| `_violation` | function | 2 | 1 | 72 | server/live_voice/task_progress_return.py |
| `_EVENTS_CAPABILITY` | constant | 1 | 1 | 1 | server/live_voice/task_progress_return.py |

### `server/live_voice/product_p3_text_adapter.py`（1,207 行；被 2 个生产文件导入；22 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductP3TextAdapter` | owner | 646 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `ProductP3ProgressCleanupHandle` | owner | 248 | 1 | 11 | server/live_voice/product_composition_registry.py |
| `ProductP3ProgressActivation` | value | 46 | 0 | 20 |  |
| `ProductP3TextReason` | value | 15 | 0 | 45 |  |
| `ProductP3CleanupSnapshot` | value | 15 | 0 | 5 |  |
| `_INACTIVE_TASK_PROGRESS_REASONS` | constant | 13 | 0 | 1 |  |
| `ProductP3ProgressRequest` | value | 12 | 1 | 4 | server/live_voice/product_composition_registry.py |
| `_NO_CLEANUP_PROGRESS_REASONS` | constant | 11 | 0 | 2 |  |
| `ProductP3AuthorizedQuery` | value | 11 | 1 | 3 | server/live_voice/p3_authenticated_composition.py |
| `_INACTIVE_PRODUCT_PROGRESS_REASONS` | constant | 10 | 0 | 1 |  |
| `ProductP3QueryRequest` | value | 9 | 1 | 4 | server/live_voice/product_composition_registry.py |
| `ProductP3QueryOwner` | value | 9 | 0 | 2 |  |
| `ProductP3SubscriptionFactory` | value | 8 | 0 | 2 |  |
| `_valid_text` | function | 8 | 0 | 13 |  |
| `ProductP3PreparedSourceFactory` | value | 6 | 0 | 1 |  |
| `ProductP3CleanupState` | value | 5 | 0 | 15 |  |
| `ProductP3CleanupReason` | value | 5 | 0 | 8 |  |
| `ProductP3QueryResult` | value | 4 | 0 | 20 |  |
| `_QUERY_OPERATIONS` | constant | 3 | 0 | 2 |  |
| `_OPTIONAL_CLEANUP_PROGRESS_REASONS` | constant | 3 | 0 | 1 |  |
| `_INACTIVE_PROGRESS_REASONS` | constant | 3 | 0 | 1 |  |
| `_MUTATION_OPERATIONS` | constant | 1 | 0 | 2 |  |

### `channels/web/frontend/src/features/live-voice/formal/productTextProgress.ts`（870 行；被 2 个生产文件导入；19 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `parseProductTextProgressEvent` | function | 166 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductTextProgressAckOwner` | class | 133 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductTextProgressDomAdoptionOwner` | class | 68 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `productTextProgressPresentationBinding` | function | 36 | 2 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx, channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `createProductTextProgressDeliveryAck` | function | 33 | 0 | 1 |  |
| `ProductTextProgressEvent` | type | 32 | 2 | 11 | channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx, channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `adoptParsedProductTextProgressEvent` | function | 29 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductTextProgressLegacyDeliveryAck` | type | 13 | 0 | 2 |  |
| `ProductTextProgressEnvelope` | type | 11 | 0 | 3 |  |
| `adoptProductTextProgressEvent` | function | 9 | 0 | 0 |  |
| `ProductTextProgressPresentationAck` | type | 8 | 0 | 1 |  |
| `ProductTextProgressScope` | type | 6 | 0 | 4 |  |
| `ProductTextProgressAckSnapshot` | type | 6 | 0 | 7 |  |
| `ProductTextProgressDomNode` | type | 4 | 0 | 1 |  |
| `PRODUCT_TEXT_PROGRESS_EVENT` | const | 1 | 1 | 3 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_PROGRESS_ACK_METHOD` | const | 1 | 0 | 2 |  |
| `ProductTextProgressDeliveryAck` | type | 1 | 0 | 5 |  |
| `ProductTextProgressAckStatus` | type | 1 | 0 | 2 |  |
| `ProductTextProgressAckRequest` | type | 1 | 0 | 2 |  |

## 12 Presentation/history（5 文件，2,063 行）

### `server/live_voice/presentation_ledger.py`（1,272 行；被 9 个生产文件导入；18 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `TaskPresentationConsumptionOwner` | owner | 488 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `PresentationLedger` | owner | 469 | 2 | 0 | server/live_voice/conversation_runtime_loop.py, server/live_voice/native_interaction_runtime.py |
| `TaskPresentationDelivery` | value | 78 | 2 | 10 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py |
| `TextPresentationAdoptionAck` | value | 39 | 1 | 5 | server/live_voice/product_composition_registry.py |
| `TaskPresentationRuntimeReceipt` | value | 35 | 3 | 3 | server/live_voice/agent_conversation_runtime.py, server/live_voice/product_composition_registry.py, server/live_voice/product_p2_interaction_adapter.py |
| `next_task_presentation_event` | function | 24 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `PresentationUnit` | value | 8 | 4 | 5 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/agent_conversation_runtime.py, server/live_voice/conversation_runtime_loop.py |
| `PresentedHistorySpan` | value | 7 | 1 | 3 | server/live_voice/conversation_runtime_loop.py |
| `PresentationLedgerSnapshot` | value | 7 | 1 | 2 | server/live_voice/conversation_runtime_loop.py |
| `TaskPresentationViolation` | exception | 6 | 1 | 51 | server/live_voice/product_composition_registry.py |
| `PresentationAck` | value | 6 | 8 | 10 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/agent_conversation_runtime.py |
| `PresentationLedgerViolation` | exception | 5 | 0 | 29 |  |
| `HistorySurfacePolicy` | value | 5 | 3 | 8 | server/live_voice/agent_conversation_runtime.py, server/live_voice/conversation_runtime_loop.py, server/live_voice/native_interaction_runtime.py |
| `PresentationState` | value | 5 | 2 | 13 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_interaction_runtime.py |
| `PresentationRecord` | value | 5 | 0 | 10 |  |
| `PresentationSurface` | value | 3 | 7 | 36 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/agent_conversation_runtime.py, server/live_voice/conversation_runtime_loop.py |
| `TaskPresentationRuntimeAuthorityPort` | constant | 3 | 0 | 1 |  |
| `_UTC_PATTERN` | constant | 1 | 0 | 2 |  |

### `server/live_voice/p2_response_generation_store.py`（436 行；被 2 个生产文件导入；7 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SqliteP2ResponseGenerationOwner` | owner | 391 | 2 | 3 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_composition_registry.py |
| `_TABLE_SCHEMA` | constant | 18 | 0 | 2 |  |
| `_SCHEMA_VERSION` | constant | 1 | 0 | 3 |  |
| `_EXACT_CAPACITY` | constant | 1 | 0 | 2 |  |
| `_FENCE_ROWS` | constant | 1 | 0 | 1 |  |
| `_FENCE_BUCKETS` | constant | 1 | 0 | 2 |  |
| `_SQLITE_INTEGER_MAX` | constant | 1 | 0 | 1 |  |

### `server/live_voice/formal_history_writer.py`（279 行；被 2 个生产文件导入；4 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SessionFormalHistoryWriter` | owner | 170 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `native_assistant_history_record` | function | 40 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `native_user_history_record` | function | 35 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `FormalHistoryWriterViolation` | exception | 4 | 0 | 16 |  |

### `server/live_voice/task_control_presentation.py`（47 行；被 1 个生产文件导入；3 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `task_status_text` | function | 19 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `adjustment_status_text` | function | 14 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `task_subject` | function | 3 | 1 | 1 | server/live_voice/product_composition_registry.py |

### `channels/web/frontend/src/features/live-voice/taskPresentationView.ts`（29 行；被 1 个生产文件导入；1 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `LiveVoiceTaskActivity` | type | 28 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx |

## 13 Formal Web/UI（12 文件，16,517 行）

### `channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`（9,814 行；被 3 个生产文件导入；59 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `LiveVoiceIntegratedRoutePanelView` | function | 457 | 0 | 1 |  |
| `classifyProductP2Notification` | function | 359 | 0 | 2 |  |
| `LiveVoiceIntegratedRoutePanelViewProps` | type | 51 | 0 | 1 |  |
| `parseProductP3RetryAdmission` | function | 37 | 0 | 1 |  |
| `ProductLiveVoiceSurfaceState` | type | 33 | 2 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx, channels/web/frontend/src/components/ChatPanel/index.tsx |
| `bindProductVoiceTaskOrigin` | function | 33 | 0 | 2 |  |
| `terminalTextFallbackNotificationText` | function | 30 | 0 | 1 |  |
| `awaitProductTaskNotificationPlayout` | function | 28 | 0 | 3 |  |
| `terminalTextFallbackMessage` | function | 25 | 0 | 1 |  |
| `normalizeProductP1StatusForP2Retirement` | function | 17 | 0 | 1 |  |
| `productVoiceDraftMatchesBinding` | function | 17 | 0 | 6 |  |
| `LiveVoiceIntegratedRoutePanelProps` | type | 16 | 0 | 4 |  |
| `ProductLiveVoiceSurfaceControl` | type | 16 | 2 | 2 | channels/web/frontend/src/components/ChatPanel/index.tsx, channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts |
| `progressMatchesOwnedBinding` | function | 16 | 0 | 2 |  |
| `isCurrentProgressOwner` | function | 16 | 0 | 1 |  |
| `resolveProductTaskCreateOrigin` | function | 15 | 0 | 1 |  |
| `terminalTextFallbackCompletesVoiceAnnouncement` | function | 15 | 0 | 1 |  |
| `ProductLiveVoiceMessageEvent` | type | 12 | 0 | 2 |  |
| `ProductLiveVoiceRecoveryDiagnostic` | type | 12 | 0 | 10 |  |
| `recognizedSpeechConfirmationMatches` | function | 12 | 0 | 1 |  |
| `RecognizedSpeechConfirmation` | type | 11 | 0 | 6 |  |
| `productRecoveryDiagnosticMatchesClear` | function | 10 | 0 | 1 |  |
| `ProductVoiceTaskOrigin` | type | 10 | 0 | 5 |  |
| `terminalAnnouncementArbitrationAction` | function | 10 | 0 | 1 |  |
| `reconcileProductP3ProgressEvent` | function | 10 | 0 | 1 |  |
| `retainBoundedPresentedProductResponse` | function | 10 | 0 | 10 |  |
| `ProductRecognizedVoice` | type | 9 | 0 | 4 |  |
| `inspectProductP3RetryCandidate` | function | 9 | 0 | 4 |  |
| `shouldBlockProductP2NotificationPoll` | function | 9 | 0 | 2 |  |
| `productP2TaskNotificationCheckRequired` | function | 9 | 0 | 2 |  |
| `rememberProductP3ProgressExhaustion` | function | 9 | 0 | 2 |  |
| `capturedTaskNotificationDeadlineAction` | function | 8 | 0 | 1 |  |
| `createProductP2ActivationOwner` | function | 7 | 0 | 4 |  |
| `ProductPresentationAckInput` | type | 7 | 0 | 7 |  |
| `bootstrapProductP3TaskInspectionLeaf` | function | 7 | 0 | 2 |  |
| `productP2WebRequestOptions` | function | 7 | 0 | 8 |  |
| `productP2NotificationRepollDelayMs` | function | 7 | 0 | 1 |  |
| `ProductP3RetryAdmission` | type | 7 | 0 | 2 |  |
| `productP2NotificationTransportBlockedByP1` | function | 5 | 0 | 2 |  |
| `productP2TaskNotificationRequiresCaptureArbitration` | function | 5 | 0 | 2 |  |

### `channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts`（2,223 行；被 4 个生产文件导入；44 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductWebP2ActivationOwner` | class | 860 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductWebP3ProgressOwner` | class | 211 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductWebP3MutationOwner` | class | 139 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `validateProductP2DurableOperation` | function | 72 | 0 | 2 |  |
| `pollProductP2RouteWithRecovery` | function | 26 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `retryRetainedProductOperation` | function | 25 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductWebP3MutationInput` | type | 15 | 1 | 6 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductWebP3ProgressSnapshot` | type | 10 | 1 | 14 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `isProductNotificationSequenceMismatch` | function | 9 | 1 | 3 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductWebP3ProgressBinding` | type | 8 | 1 | 5 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `isRetriableProductOperationError` | function | 8 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductWebP3ConfirmationReceipt` | type | 8 | 0 | 4 |  |
| `replayProductP2DurableOperation` | function | 8 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductWebP2ActivationBinding` | type | 7 | 4 | 16 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx, channels/web/frontend/src/features/live-voice/formal/nativeGeneratedText.ts, channels/web/frontend/src/features/live-voice/formal/nativeWorkState.ts |
| `isDefinitiveProductOperationError` | function | 7 | 1 | 9 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductWebP3TaskControlBinding` | type | 7 | 0 | 2 |  |
| `ProductWebP2ActivationSnapshot` | type | 6 | 1 | 16 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `requiresProductActivationCleanup` | function | 6 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductWebCloseRetryOptions` | type | 5 | 0 | 3 |  |
| `ProductP2DurableOperationMethod` | type | 5 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/productP2ActivationJournal.ts |
| `ProductP2DurableOperation` | type | 5 | 1 | 7 | channels/web/frontend/src/features/live-voice/formal/productP2ActivationJournal.ts |
| `ProductAgentModelSelection` | type | 4 | 0 | 4 |  |
| `ProductConfirmedAgentModelSelection` | type | 4 | 0 | 3 |  |
| `ProductP2DurableOperationJournal` | type | 4 | 1 | 2 | channels/web/frontend/src/features/live-voice/formal/productP2ActivationJournal.ts |
| `ProductP2CloseCause` | type | 2 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductP2PollRecoveryResult` | type | 2 | 0 | 1 |  |
| `PRODUCT_P2_ACTIVATE_METHOD` | const | 1 | 0 | 2 |  |
| `PRODUCT_P2_CLOSE_METHOD` | const | 1 | 0 | 1 |  |
| `PRODUCT_P2_SUBMIT_METHOD` | const | 1 | 1 | 7 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_P2_NOTIFICATION_NEXT_METHOD` | const | 1 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_P2_PRESENTATION_ACK_METHOD` | const | 1 | 1 | 7 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_P2_PRESENTATION_FAILED_METHOD` | const | 1 | 0 | 1 |  |
| `PRODUCT_P2_BARGE_IN_METHOD` | const | 1 | 0 | 4 |  |
| `PRODUCT_P2_INTERRUPT_GENERATION_METHOD` | const | 1 | 0 | 7 |  |
| `PRODUCT_P3_CONFIRMATION_ISSUE_METHOD` | const | 1 | 0 | 1 |  |
| `PRODUCT_P3_MUTATE_METHOD` | const | 1 | 0 | 1 |  |
| `PRODUCT_P3_TASK_LIST_METHOD` | const | 1 | 0 | 1 |  |
| `PRODUCT_P3_TASK_STATUS_METHOD` | const | 1 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_P3_TASK_EVENTS_METHOD` | const | 1 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_P3_PROGRESS_ACTIVATE_METHOD` | const | 1 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |

### `channels/web/frontend/src/features/live-voice/formal/productP2ActivationJournal.ts`（1,314 行；被 1 个生产文件导入；13 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductP2ActivationJournal` | class | 376 | 1 | 5 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductP2ActivationJournalSnapshot` | type | 16 | 0 | 5 |  |
| `reconcileProductP2Predecessor` | function | 13 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductP2ActivationJournalPhase` | type | 12 | 0 | 11 |  |
| `reconcileRetiredProductP2PresentationAcks` | function | 9 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductP2RecoveryClaim` | type | 5 | 0 | 14 |  |
| `ProductP2RetiredPresentationAckRecoveryResult` | type | 4 | 0 | 2 |  |
| `ProductP2RecoveryLease` | type | 3 | 0 | 3 |  |
| `ProductP2PredecessorRecoveryResult` | type | 2 | 0 | 8 |  |
| `PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA` | const | 1 | 0 | 7 |  |
| `PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED` | const | 1 | 1 | 9 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `PRODUCT_P2_REFRESH_SERVER_STATE_LOST` | const | 1 | 1 | 3 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductP2ActivationJournalStore` | type | 1 | 0 | 4 |  |

### `channels/web/frontend/src/features/live-voice/formal/formalP3TaskExperience.ts`（972 行；被 3 个生产文件导入；12 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `FormalP3TaskExperienceOwner` | class | 467 | 2 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx, channels/web/frontend/src/stores/liveVoiceTaskStore.ts |
| `FormalP3TaskRecord` | type | 28 | 1 | 18 | channels/web/frontend/src/stores/liveVoiceTaskStore.ts |
| `FormalP3TaskCommand` | type | 14 | 0 | 6 |  |
| `FORMAL_P3_TASK_OPERATIONS` | const | 12 | 0 | 2 |  |
| `FormalP3TaskDisplayState` | type | 11 | 0 | 2 |  |
| `FORMAL_P3_TASK_METHODS` | const | 9 | 0 | 7 |  |
| `FormalP3TaskExperienceSnapshot` | type | 9 | 3 | 19 | channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx, channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx, channels/web/frontend/src/stores/liveVoiceTaskStore.ts |
| `FormalP3TaskCommandPhase` | type | 8 | 0 | 2 |  |
| `FormalP3TaskMutationInput` | type | 8 | 1 | 7 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `FormalP3TaskRequest` | type | 5 | 0 | 2 |  |
| `FormalP3TaskOperation` | type | 1 | 0 | 9 |  |
| `FormalP3TaskSelectionStore` | type | 1 | 0 | 5 |  |

### `channels/web/frontend/src/features/live-voice/formal/formalTaskControlLeaf.ts`（952 行；被 2 个生产文件导入；18 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `FormalTaskControlLeaf` | class | 533 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `prepareFormalTaskMutation` | function | 34 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `FormalTaskControlRecord` | type | 10 | 1 | 7 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `FormalTaskProgressOrigin` | type | 10 | 0 | 1 |  |
| `isFormalTaskRetryEligible` | function | 10 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `FormalTaskControlSnapshot` | type | 9 | 0 | 5 |  |
| `FORMAL_TASK_CONTROL_LIMITS` | const | 8 | 0 | 12 |  |
| `FormalTaskControlBinding` | type | 7 | 2 | 12 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx, channels/web/frontend/src/features/live-voice/formal/productP3TaskTargetJournal.ts |
| `FormalTaskConfirmationReceipt` | type | 7 | 0 | 2 |  |
| `FormalTaskAdoptionContext` | type | 6 | 0 | 2 |  |
| `FormalTaskMutationInput` | type | 5 | 0 | 2 |  |
| `PreparedFormalTaskMutation` | type | 5 | 1 | 3 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `FormalTaskEventsQueryContext` | type | 4 | 0 | 3 |  |
| `mapFormalTaskCancel` | function | 4 | 0 | 0 |  |
| `FORMAL_TASK_CONTROL_OPERATIONS` | const | 1 | 0 | 1 |  |
| `FormalTaskControlOperation` | type | 1 | 0 | 2 |  |
| `FormalTaskCancelScope` | type | 1 | 0 | 1 |  |
| `FormalTaskState` | type | 1 | 1 | 12 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |

### `channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts`（587 行；被 1 个生产文件导入；19 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `IntegratedWebRouteShell` | class | 255 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `createCurrentIntegratedWebRouteSelection` | function | 89 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `IntegratedWebAdapterRegistry` | class | 21 | 0 | 4 |  |
| `IntegratedWebRouteAdapter` | type | 13 | 0 | 8 |  |
| `IntegratedWebRouteManifest` | type | 11 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `CurrentIntegratedWebRouteFacts` | type | 10 | 0 | 1 |  |
| `IntegratedWebRouteViolation` | class | 9 | 0 | 30 |  |
| `IntegratedWebSegmentRoute` | type | 7 | 0 | 6 |  |
| `IntegratedWebRouteContext` | type | 5 | 0 | 5 |  |
| `IntegratedWebRouteActivationContext` | type | 4 | 0 | 1 |  |
| `IntegratedWebFaultPlan` | type | 4 | 0 | 1 |  |
| `IntegratedWebRouteSelection` | type | 4 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `IntegratedWebRouteLease` | type | 3 | 0 | 7 |  |
| `INTEGRATED_WEB_SEGMENTS` | const | 1 | 0 | 5 |  |
| `IntegratedWebSegmentId` | type | 1 | 0 | 16 |  |
| `IntegratedWebRequestedClass` | type | 1 | 0 | 7 |  |
| `IntegratedWebCompositionState` | type | 1 | 0 | 2 |  |
| `IntegratedWebWiringState` | type | 1 | 0 | 1 |  |
| `IntegratedWebRoutePolicy` | type | 1 | 0 | 3 |  |

### `channels/web/frontend/src/features/live-voice/formal/productP3ProgressGenerationJournal.ts`（236 行；被 1 个生产文件导入；4 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductP3ProgressGenerationIdentity` | type | 7 | 0 | 4 |  |
| `claimProductP3ProgressGeneration` | function | 6 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductP3ProgressGenerationLease` | type | 3 | 0 | 2 |  |
| `ProductP3ProgressGenerationJournalStore` | type | 1 | 0 | 2 |  |

### `channels/web/frontend/src/features/live-voice/formal/productP3TaskTargetJournal.ts`（148 行；被 1 个生产文件导入；6 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `persistProductP3TaskTarget` | function | 12 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `ProductP3TaskTargetJournalRecord` | type | 7 | 0 | 4 |  |
| `ProductP3TaskTargetJournalInspection` | type | 2 | 0 | 1 |  |
| `inspectProductP3TaskTarget` | function | 2 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `readProductP3TaskTarget` | function | 2 | 0 | 0 |  |
| `ProductP3TaskTargetJournalStore` | type | 1 | 0 | 4 |  |

### `channels/web/frontend/src/components/ChatPanel/useProductVoiceSessionStart.ts`（99 行；被 1 个生产文件导入；2 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `useProductVoiceSessionStart` | function | 93 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/index.tsx |
| `PrepareProductVoiceSession` | type | 1 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/index.tsx |

### `channels/web/frontend/src/components/ToolPanel/RecentTasksPanel.tsx`（70 行；被 1 个生产文件导入；1 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `RecentTasksPanel` | function | 64 | 1 | 0 | channels/web/frontend/src/components/ToolPanel/index.tsx |

### `channels/web/frontend/src/multi-session/state/createLiveVoiceConversation.ts`（55 行；被 2 个生产文件导入；2 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `createLiveVoiceConversation` | function | 48 | 2 | 0 | channels/web/frontend/src/App.tsx, channels/web/frontend/src/components/ChatPanel/useProductVoiceSessionStart.ts |
| `LiveVoiceProjectRequiredError` | class | 1 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/useProductVoiceSessionStart.ts |

### `channels/web/frontend/src/features/live-voice/formal/taskNotificationIdentity.ts`（47 行；被 4 个生产文件导入；4 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `coalesceTaskNotifications` | function | 16 | 2 | 0 | channels/web/frontend/src/features/chatTimeline/buildTurnTimeline.ts, channels/web/frontend/src/stores/chatStore.ts |
| `taskNotificationBindingKey` | function | 10 | 1 | 1 | channels/web/frontend/src/features/historyRestore.ts |
| `taskNotificationSourceKey` | function | 8 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `TaskNotificationDisplay` | type | 4 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |

## 14 Composition/config（6 文件，20,076 行）

### `server/live_voice/product_composition_registry.py`（16,070 行；被 2 个生产文件导入；61 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `AgentServerProductCompositionRegistry` | owner | 15059 | 0 | 4 |  |
| `_project_production_status_authority` | function | 112 | 0 | 1 |  |
| `create_product_composition_registry_from_environment` | function | 34 | 1 | 1 | server/agent_ws_server.py |
| `_P2FailedCleanupLease` | owner | 26 | 0 | 4 |  |
| `_error_result` | function | 25 | 1 | 174 | server/live_voice/native_business_router.py |
| `_P2RootLease` | owner | 24 | 0 | 1 |  |
| `_P2Route` | value | 22 | 0 | 30 |  |
| `_project_production_collection_authority` | function | 21 | 0 | 1 |  |
| `PRODUCT_COMPOSITION_METHODS` | constant | 20 | 0 | 1 |  |
| `ProductCompositionSettings` | value | 20 | 0 | 5 |  |
| `_formal_live_voice_capable` | function | 19 | 0 | 1 |  |
| `_RetainedProductOperation` | value | 18 | 0 | 28 |  |
| `_ProgressDelivery` | value | 17 | 0 | 20 |  |
| `_ProgressRoute` | value | 16 | 0 | 7 |  |
| `_PendingProductionTaskIntent` | value | 16 | 0 | 12 |  |
| `_required_content` | function | 16 | 0 | 2 |  |
| `_formal_fact` | function | 15 | 0 | 7 |  |
| `_serialize_manifest` | function | 15 | 0 | 4 |  |
| `_success_result` | function | 15 | 1 | 38 | server/live_voice/native_business_router.py |
| `_TASK_RESULT_ARTIFACT_STATUSES` | constant | 14 | 0 | 1 |  |
| `_unavailable_fact` | function | 13 | 0 | 14 |  |
| `_require_exact_params` | function | 10 | 0 | 18 |  |
| `_SingleCandidateResolver` | owner | 10 | 0 | 1 |  |
| `_RejectingProductionConfirmationConsumer` | class | 9 | 1 | 1 | server/live_voice/native_business_router.py |
| `_AuthorityLease` | owner | 8 | 0 | 1 |  |
| `_P3FailedCleanupLease` | owner | 8 | 0 | 1 |  |
| `_required_text` | function | 8 | 0 | 122 |  |
| `_bind_unified_response_request` | function | 8 | 0 | 6 |  |
| `_ProgressTarget` | value | 7 | 0 | 2 |  |
| `_TaskPresentationFallback` | value | 7 | 0 | 3 |  |
| `_VoiceTaskOrigin` | value | 7 | 1 | 8 | server/live_voice/native_business_router.py |
| `_best_effort_l0_binding` | function | 7 | 0 | 2 |  |
| `_AuthorityState` | value | 5 | 0 | 13 |  |
| `_ClosedProgressRoute` | value | 5 | 0 | 3 |  |
| `product_composition_enabled_from_environment` | function | 4 | 0 | 2 |  |
| `_L0CommitAdmissionClock` | value | 4 | 0 | 7 |  |
| `_ClosedP2Route` | value | 4 | 0 | 7 |  |
| `_PendingProgressPresentation` | value | 4 | 0 | 2 |  |
| `_optional_claim` | function | 4 | 0 | 2 |  |
| `_PRODUCT_P2_PRESENTATION_FAILURE_OPERATION` | constant | 3 | 0 | 1 |  |

### `server/live_voice/product_p2_interaction_adapter.py`（2,117 行；被 2 个生产文件导入；34 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `P2ActivationLease` | owner | 982 | 1 | 5 | server/live_voice/product_composition_registry.py |
| `ProductP2InteractionAdapter` | owner | 465 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `P2FailedActivationCleanup` | class | 120 | 1 | 7 | server/live_voice/product_composition_registry.py |
| `P2ActivationResult` | value | 101 | 0 | 21 |  |
| `P2InteractionBinding` | value | 35 | 1 | 48 | server/live_voice/product_composition_registry.py |
| `P2PreparedActivation` | value | 34 | 0 | 7 |  |
| `_route_fingerprint` | function | 31 | 0 | 2 |  |
| `P2InteractionActivationRequest` | value | 26 | 1 | 9 | server/live_voice/product_composition_registry.py |
| `P2FoundationEvidence` | value | 19 | 0 | 4 |  |
| `_authority_activity` | function | 17 | 0 | 2 |  |
| `_require_text` | function | 16 | 0 | 6 |  |
| `_require_timeout` | function | 13 | 0 | 4 |  |
| `P2ActivationReason` | value | 12 | 1 | 36 | server/live_voice/product_composition_registry.py |
| `_CANCELLATION_SCOPES` | constant | 9 | 0 | 1 |  |
| `_require_generation` | function | 8 | 0 | 2 |  |
| `_P2RuntimePort` | value | 8 | 0 | 8 |  |
| `ProductP2AdapterViolation` | exception | 7 | 1 | 3 | server/live_voice/product_composition_registry.py |
| `P2InteractionIntent` | value | 7 | 0 | 3 |  |
| `P2ActivationStatus` | value | 6 | 1 | 25 | server/live_voice/product_composition_registry.py |
| `P2CancellationScope` | value | 5 | 0 | 6 |  |
| `P2LeaseState` | value | 5 | 2 | 12 | server/live_voice/native_business_router.py, server/live_voice/product_composition_registry.py |
| `P2ActivationLeaseSnapshot` | value | 5 | 0 | 3 |  |
| `P2LeaseCloseStatus` | value | 4 | 1 | 22 | server/live_voice/product_composition_registry.py |
| `P2FailedActivationCleanupSnapshot` | value | 4 | 0 | 3 |  |
| `P2LeaseCloseResult` | value | 3 | 0 | 16 |  |
| `P2RuntimeFactory` | constant | 3 | 0 | 1 |  |
| `P2InteractionEngineFactory` | constant | 3 | 0 | 1 |  |
| `_violation` | function | 2 | 0 | 85 |  |
| `_utc_now` | function | 2 | 0 | 1 |  |
| `_P2_OPERATION` | constant | 1 | 0 | 3 |  |
| `_P2_CAPABILITIES` | constant | 1 | 0 | 2 |  |
| `_MAX_NOTIFICATION_BATCH` | constant | 1 | 0 | 1 |  |
| `P2_FOUNDATION_EVIDENCE` | constant | 1 | 0 | 3 |  |
| `_PREPARED_ACTIVATION_TOKEN` | constant | 1 | 0 | 2 |  |

### `server/live_voice/live_voice_configuration_declaration.py`（1,003 行；被 2 个生产文件导入；40 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `LiveVoiceCapabilityDeclaration` | value | 135 | 1 | 8 | server/live_voice/product_observability_runtime.py |
| `ValidatedLiveVoiceConfiguration` | value | 125 | 2 | 11 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_observability_runtime.py |
| `evaluate_live_voice_capability_declaration_replay` | function | 61 | 0 | 1 |  |
| `_configuration_fingerprint` | function | 59 | 0 | 2 |  |
| `ConfigurationDeclarationResult` | value | 51 | 0 | 8 |  |
| `_validated_configuration` | function | 49 | 0 | 3 |  |
| `ConfigurationReplayResult` | value | 48 | 0 | 9 |  |
| `declare_live_voice_capabilities` | function | 48 | 1 | 1 | server/live_voice/product_observability_runtime.py |
| `_build_declaration` | function | 28 | 0 | 2 |  |
| `_validation_receipts` | function | 27 | 0 | 2 |  |
| `ValidatedExecutorConfiguration` | value | 26 | 1 | 7 | server/live_voice/p3_authenticated_composition.py |
| `_validated_executor` | function | 23 | 0 | 1 |  |
| `_REQUIRED_EXECUTOR_CAPABILITIES` | constant | 19 | 0 | 1 |  |
| `ValidatedProviderConfiguration` | value | 19 | 2 | 5 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_observability_runtime.py |
| `_canonical_enum_tuple` | function | 18 | 0 | 4 |  |
| `ValidatedAuthenticationConfiguration` | value | 18 | 1 | 7 | server/live_voice/p3_authenticated_composition.py |
| `_PROVIDER_CAPABILITY` | constant | 15 | 0 | 2 |  |
| `_validated_authentication` | function | 14 | 0 | 1 |  |
| `LiveVoiceCapability` | value | 13 | 2 | 24 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_observability_runtime.py |
| `_safe_identity` | function | 12 | 0 | 10 |  |
| `_validated_declaration` | function | 10 | 0 | 2 |  |
| `ExecutorCapability` | value | 7 | 1 | 13 | server/live_voice/p3_authenticated_composition.py |
| `ProviderCapability` | value | 6 | 2 | 9 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_observability_runtime.py |
| `ConfigurationDeclarationReason` | value | 6 | 0 | 10 |  |
| `ConfigurationReplayReason` | value | 6 | 0 | 11 |  |
| `_DURABILITY_CAPABILITY` | constant | 5 | 0 | 4 |  |
| `DurabilityLevel` | value | 4 | 1 | 11 | server/live_voice/p3_authenticated_composition.py |
| `_digest` | function | 4 | 0 | 5 |  |
| `LIVE_VOICE_CONFIGURATION_CONTRACT_VERSION` | constant | 3 | 1 | 2 | server/live_voice/p3_authenticated_composition.py |
| `LIVE_VOICE_CAPABILITY_DECLARATION_VERSION` | constant | 3 | 0 | 3 |  |
| `LiveVoiceDeploymentProfile` | value | 3 | 2 | 7 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_observability_runtime.py |
| `AuthenticationMode` | value | 3 | 2 | 11 | server/live_voice/p3_authenticated_composition.py, server/live_voice/product_observability_runtime.py |
| `ConfigurationContractViolation` | exception | 2 | 0 | 23 |  |
| `PrivateConfigurationContent` | class | 2 | 0 | 3 |  |
| `CapabilityConfigurationConflict` | class | 2 | 0 | 15 |  |
| `MAX_CONFIGURED_PROVIDERS` | constant | 1 | 0 | 2 |  |
| `_IDENTITY` | constant | 1 | 0 | 1 |  |
| `_DIGEST` | constant | 1 | 0 | 1 |  |
| `_EMAIL` | constant | 1 | 0 | 1 |  |
| `_PHONE` | constant | 1 | 0 | 1 |  |

### `server/live_voice/product_composition_root.py`（459 行；被 2 个生产文件导入；16 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductCompositionRoot` | class | 211 | 2 | 1 | server/live_voice/product_composition_registry.py, server/live_voice/product_observability_adapter.py |
| `ProductCompositionLease` | owner | 46 | 1 | 7 | server/live_voice/product_composition_registry.py |
| `ProductSegmentActivation` | value | 22 | 1 | 3 | server/live_voice/product_composition_registry.py |
| `ProductSegmentActivationError` | exception | 19 | 1 | 2 | server/live_voice/product_composition_registry.py |
| `ProductCompositionRegistration` | value | 15 | 1 | 6 | server/live_voice/product_composition_registry.py |
| `ProductCompositionActivationError` | exception | 12 | 1 | 4 | server/live_voice/product_composition_registry.py |
| `_registered_but_inactive` | function | 10 | 0 | 1 |  |
| `_authority_unavailable` | function | 10 | 0 | 2 |  |
| `ProductCompositionContext` | value | 7 | 2 | 5 | server/live_voice/product_composition_registry.py, server/live_voice/product_observability_adapter.py |
| `ProductCompositionLeaseCloseError` | exception | 6 | 1 | 4 | server/live_voice/product_composition_registry.py |
| `SegmentActivationCallback` | constant | 4 | 0 | 2 |  |
| `ProductCompositionActivation` | value | 4 | 0 | 5 |  |
| `_required_text` | function | 4 | 1 | 4 | server/live_voice/product_composition_registry.py |
| `_RetainedSegmentLease` | value | 3 | 0 | 4 |  |
| `ProductCompositionRootViolation` | exception | 2 | 1 | 19 | server/live_voice/product_observability_adapter.py |
| `SegmentLease` | value | 2 | 0 | 4 |  |

### `server/live_voice/product_composition_contract.py`（424 行；被 3 个生产文件导入；15 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductRouteFact` | value | 82 | 3 | 16 | server/live_voice/product_composition_registry.py, server/live_voice/product_composition_root.py, server/live_voice/product_observability_adapter.py |
| `route_fact_from_integrated_shell` | function | 66 | 0 | 0 |  |
| `create_product_composition_manifest` | function | 46 | 2 | 0 | server/live_voice/product_composition_registry.py, server/live_voice/product_composition_root.py |
| `_FORBIDDEN_EVIDENCE_BY_TRUTH` | constant | 41 | 0 | 1 |  |
| `ProductCompositionManifest` | value | 36 | 2 | 3 | server/live_voice/product_composition_registry.py, server/live_voice/product_composition_root.py |
| `ProductRouteReason` | value | 25 | 3 | 19 | server/live_voice/product_composition_registry.py, server/live_voice/product_composition_root.py, server/live_voice/product_observability_adapter.py |
| `ProductEvidenceId` | value | 24 | 3 | 38 | server/live_voice/product_composition_registry.py, server/live_voice/product_composition_root.py, server/live_voice/product_observability_adapter.py |
| `_REASON_BY_TRUTH` | constant | 21 | 0 | 1 |  |
| `ProductSegment` | value | 9 | 3 | 13 | server/live_voice/product_composition_registry.py, server/live_voice/product_composition_root.py, server/live_voice/product_observability_adapter.py |
| `_FORMAL_STOP_CLOSURE_BY_SEGMENT` | constant | 8 | 0 | 1 |  |
| `_FORMAL_EVIDENCE` | constant | 7 | 0 | 3 |  |
| `_disabled_fact` | function | 7 | 0 | 2 |  |
| `ProductRouteTruth` | value | 6 | 3 | 27 | server/live_voice/product_composition_registry.py, server/live_voice/product_composition_root.py, server/live_voice/product_observability_adapter.py |
| `ProductCompositionContractViolation` | exception | 2 | 2 | 29 | server/live_voice/product_composition_root.py, server/live_voice/product_observability_adapter.py |
| `PRODUCT_COMPOSITION_CONTRACT_VERSION` | constant | 1 | 0 | 3 |  |

### `server/live_voice/__init__.py`（3 行；被 0 个生产文件导入；0 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|

## 15 Observability（25 文件，16,800 行）

### `server/live_voice/latency_measurement.py`（1,972 行；被 3 个生产文件导入；80 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `_MARKER_RULES` | constant | 212 | 0 | 3 |  |
| `validate_l0_corpus_manifest` | function | 185 | 0 | 2 |  |
| `build_l0_measurement_report` | function | 146 | 0 | 1 |  |
| `L0MeasurementCollector` | owner | 106 | 0 | 3 |  |
| `_round_summary` | function | 103 | 0 | 1 |  |
| `create_l0_milestone` | function | 88 | 0 | 2 |  |
| `L0MeasurementEnvelope` | value | 68 | 0 | 19 |  |
| `L0RoundBinding` | value | 66 | 2 | 24 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/product_composition_registry.py |
| `emit_runtime_l0_milestone` | function | 63 | 3 | 1 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/agent_bridge_runtime.py, server/live_voice/product_composition_registry.py |
| `runtime_l0_run_labels` | function | 57 | 0 | 3 |  |
| `register_runtime_l0_binding` | function | 52 | 2 | 1 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/product_composition_registry.py |
| `_SPAN_DEFINITIONS` | constant | 42 | 0 | 2 |  |
| `L0ProcessJsonlSink` | class | 37 | 0 | 4 |  |
| `declarations_from_records` | function | 36 | 0 | 2 |  |
| `L0Milestone` | value | 34 | 3 | 99 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/agent_bridge_runtime.py, server/live_voice/product_composition_registry.py |
| `_classification_for` | function | 30 | 0 | 1 |  |
| `_binding_is_compatible` | function | 28 | 0 | 4 |  |
| `load_l0_jsonl` | function | 26 | 0 | 1 |  |
| `resolve_runtime_l0_binding` | function | 25 | 1 | 1 | server/live_voice/agent_bridge_runtime.py |
| `_registered_runtime_l0_binding` | function | 24 | 0 | 1 |  |
| `_rule` | function | 23 | 0 | 33 |  |
| `create_l0_measurement_envelope` | function | 23 | 0 | 5 |  |
| `L0RoundDeclaration` | value | 22 | 0 | 11 |  |
| `_COMMON_SUCCESS_REQUIRED` | constant | 20 | 0 | 1 |  |
| `_binding_matches_declaration` | function | 20 | 0 | 1 |  |
| `create_l0_round_binding` | function | 17 | 0 | 7 |  |
| `process_l0_sink` | function | 17 | 0 | 2 |  |
| `_QUALITY_MILESTONES` | constant | 13 | 0 | 4 |  |
| `_closed_mapping` | function | 13 | 0 | 5 |  |
| `_merge_binding` | function | 11 | 0 | 3 |  |
| `load_l0_corpus_manifest` | function | 11 | 0 | 1 |  |
| `_MarkerRule` | value | 10 | 0 | 3 |  |
| `_utc_timestamp` | function | 10 | 0 | 1 |  |
| `canonical_json_bytes` | function | 9 | 3 | 3 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/agent_bridge_runtime.py, server/live_voice/product_composition_registry.py |
| `_safe_uint` | function | 8 | 1 | 11 | gateway/live_voice/dedicated_media_registration.py |
| `_safe_number` | function | 7 | 0 | 2 |  |
| `L0CollectorStats` | value | 7 | 0 | 3 |  |
| `L0MeasurementViolation` | exception | 6 | 0 | 4 |  |
| `L0RoundClassification` | value | 6 | 2 | 26 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/agent_bridge_runtime.py |
| `L0EvidenceSource` | value | 6 | 0 | 13 |  |

### `server/live_voice/observability.py`（1,960 行；被 15 个生产文件导入；83 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `LiveVoiceObservation` | value | 252 | 8 | 15 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/latency_measurement.py, server/live_voice/observability_exporter.py |
| `LiveVoiceMetric` | value | 203 | 8 | 13 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/alpha_benchmark.py, server/live_voice/observability_exporter.py |
| `EVENT_SEMANTIC_MATRIX` | constant | 178 | 0 | 2 |  |
| `LiveVoiceObservabilityCollector` | owner | 140 | 2 | 1 | gateway/channel_manager/web/app_web_handlers.py, gateway/live_voice/dedicated_media_registration.py |
| `observation_from_task_outbox` | function | 62 | 0 | 1 |  |
| `METRIC_SEMANTIC_MATRIX` | constant | 60 | 0 | 2 |  |
| `TraceBinding` | value | 51 | 1 | 16 | server/live_voice/product_observability_adapter.py |
| `RouteDescriptor` | value | 51 | 1 | 17 | server/live_voice/product_observability_adapter.py |
| `observation_from_task_event` | function | 46 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `contains_private_observability_content` | function | 30 | 6 | 4 | server/live_voice/latency_measurement.py, server/live_voice/live_voice_configuration_declaration.py, server/live_voice/observability_correlation_contract.py |
| `create_queue_metric` | function | 29 | 0 | 1 |  |
| `FAILURE_ERROR_MATRIX` | constant | 28 | 0 | 2 |  |
| `_semantic_rule` | function | 27 | 0 | 21 |  |
| `OBSERVED_STATES` | constant | 24 | 1 | 3 | server/live_voice/observability_correlation_contract.py |
| `_closed_dict` | function | 24 | 0 | 4 |  |
| `EVENT_NAMES` | constant | 23 | 0 | 2 |  |
| `_metric_rule` | function | 23 | 0 | 8 |  |
| `REASON_CODES` | constant | 22 | 1 | 4 | server/live_voice/observability_correlation_contract.py |
| `SEGMENT_NAMES` | constant | 19 | 1 | 4 | server/live_voice/observability_correlation_contract.py |
| `_opaque_identity` | function | 19 | 0 | 5 |  |
| `SEGMENT_BINDING_MATRIX` | constant | 19 | 0 | 2 |  |
| `IDENTITY_POLICY` | constant | 18 | 0 | 1 |  |
| `_validate_cancel_target` | function | 18 | 0 | 2 |  |
| `_validate_failure_target` | function | 18 | 0 | 2 |  |
| `create_route_descriptor` | function | 18 | 0 | 5 |  |
| `route_descriptor_from_route_record` | function | 18 | 0 | 1 |  |
| `_LIFECYCLE_SEGMENTS` | constant | 17 | 0 | 4 |  |
| `_utc_timestamp` | function | 17 | 1 | 4 | server/live_voice/latency_measurement.py |
| `ERROR_CODES` | constant | 16 | 1 | 10 | server/live_voice/observability_correlation_contract.py |
| `_FAILURE_SEGMENTS` | constant | 15 | 0 | 7 |  |
| `_METRIC_REQUIRED` | constant | 15 | 0 | 1 |  |
| `FAILURE_SEGMENT_MATRIX` | constant | 14 | 0 | 2 |  |
| `_validate_required_bindings` | function | 14 | 0 | 3 |  |
| `_OBSERVATION_REQUIRED` | constant | 13 | 0 | 1 |  |
| `METRIC_DEFINITIONS` | constant | 12 | 0 | 2 |  |
| `_required_text` | function | 12 | 1 | 6 | server/live_voice/product_composition_registry.py |
| `create_observation` | function | 12 | 7 | 4 | gateway/live_voice/dedicated_media_registration.py, server/agent_ws_server.py, server/live_voice/latency_measurement.py |
| `create_metric` | function | 12 | 6 | 3 | gateway/live_voice/dedicated_media_registration.py, server/agent_ws_server.py, server/live_voice/alpha_benchmark.py |
| `_uint` | function | 11 | 0 | 6 |  |
| `_optional_member` | function | 11 | 0 | 10 |  |

### `channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts`（1,598 行；被 1 个生产文件导入；53 个顶层 symbol，其中 3 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `EVENT_SEMANTIC_MATRIX` | const | 154 | 0 | 1 |  |
| `LiveVoiceObservabilityCollector` | class | 152 | 0 | 1 |  |
| `createBrowserAudioObservabilityObserver` | function | 64 | 0 | 0 |  |
| `createMetric` | function | 51 | 0 | 1 |  |
| `METRIC_SEMANTIC_MATRIX` | const | 49 | 0 | 1 |  |
| `createObservation` | function | 43 | 1 | 2 | channels/web/frontend/src/features/live-voice/formal/l0Measurement.ts |
| `createRouteDescriptor` | function | 32 | 0 | 4 |  |
| `createTraceBinding` | function | 27 | 0 | 6 |  |
| `observationFromRouteRecord` | function | 25 | 0 | 0 |  |
| `OBSERVED_STATES` | const | 24 | 0 | 2 |  |
| `EVENT_NAMES` | const | 23 | 0 | 2 |  |
| `LiveVoiceObservationInput` | type | 23 | 0 | 3 |  |
| `LiveVoiceObservation` | type | 23 | 1 | 12 | channels/web/frontend/src/features/live-voice/formal/l0Measurement.ts |
| `REASON_CODES` | const | 22 | 0 | 4 |  |
| `SEGMENT_NAMES` | const | 19 | 0 | 4 |  |
| `LiveVoiceMetricInput` | type | 17 | 0 | 2 |  |
| `LiveVoiceMetric` | type | 17 | 0 | 10 |  |
| `SEGMENT_BINDING_MATRIX` | const | 17 | 0 | 1 |  |
| `ERROR_CODES` | const | 16 | 0 | 10 |  |
| `EventSemanticRule` | type | 12 | 0 | 3 |  |
| `METRIC_DEFINITIONS` | const | 10 | 0 | 2 |  |
| `MetricSemanticRule` | type | 10 | 0 | 2 |  |
| `TraceBindingInput` | type | 10 | 0 | 8 |  |
| `TraceBinding` | type | 10 | 0 | 15 |  |
| `routeDescriptorFromRouteRecord` | function | 10 | 0 | 1 |  |
| `LiveVoiceCollectorStats` | type | 9 | 0 | 1 |  |
| `ObservabilityViolation` | class | 9 | 0 | 3 |  |
| `FAILURE_ERROR_MATRIX` | const | 8 | 0 | 1 |  |
| `FAILURE_SEGMENT_MATRIX` | const | 8 | 0 | 1 |  |
| `RouteDescriptorInput` | type | 7 | 0 | 6 |  |
| `RouteDescriptor` | type | 7 | 0 | 9 |  |
| `BrowserAudioObservabilityOptions` | type | 7 | 0 | 4 |  |
| `IDENTITY_POLICY` | const | 6 | 0 | 0 |  |
| `CANCEL_TARGET_SEGMENT_MATRIX` | const | 6 | 0 | 2 |  |
| `OBSERVABILITY_SCHEMA_VERSION` | const | 1 | 1 | 8 | channels/web/frontend/src/features/live-voice/formal/l0Measurement.ts |
| `DEFAULT_COLLECTOR_CAPACITY` | const | 1 | 0 | 2 |  |
| `IDENTITY_MAX_LENGTH` | const | 1 | 0 | 2 |  |
| `ROUTE_IMPLEMENTATION_CLASSES` | const | 1 | 0 | 3 |  |
| `ObservedRouteClass` | type | 1 | 0 | 7 |  |
| `CANCEL_SCOPES` | const | 1 | 0 | 8 |  |

### `server/live_voice/product_observability_runtime.py`（1,425 行；被 2 个生产文件导入；30 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductObservabilityRuntime` | owner | 359 | 1 | 3 | server/live_voice/product_composition_registry.py |
| `TrustedCorrelationProjectionOwner` | owner | 169 | 0 | 5 |  |
| `ProductOtelBackendRecord` | value | 163 | 0 | 5 |  |
| `BoundedInMemoryOtelBackend` | class | 90 | 1 | 4 | server/agent_ws_server.py |
| `create_product_observability_runtime_from_environment` | function | 53 | 1 | 1 | server/agent_ws_server.py |
| `ProductOtelBackendEnvelope` | value | 52 | 0 | 6 |  |
| `_product_backend_record` | function | 50 | 0 | 1 |  |
| `_validated_runtime_declaration` | function | 48 | 0 | 1 |  |
| `_public_source_fact` | function | 45 | 0 | 1 |  |
| `ProductDiagnosticIdentity` | value | 31 | 2 | 7 | server/agent_ws_server.py, server/live_voice/product_composition_registry.py |
| `_inferred_diagnostic` | function | 28 | 0 | 1 |  |
| `_metric_dimensions` | function | 26 | 0 | 1 |  |
| `_raw_correlation_values` | function | 23 | 0 | 1 |  |
| `_trace_context` | function | 19 | 0 | 1 |  |
| `_TOKEN_FIELDS` | constant | 18 | 0 | 4 |  |
| `_IDENTITY_KIND_BY_FIELD` | constant | 18 | 0 | 1 |  |
| `ProductDiagnosticSeam` | value | 17 | 2 | 10 | server/agent_ws_server.py, server/live_voice/product_composition_registry.py |
| `ProductObservabilityRuntimeHealth` | value | 17 | 0 | 5 |  |
| `product_observability_enabled_from_environment` | function | 9 | 0 | 1 |  |
| `_requires_explicit_diagnostic` | function | 8 | 0 | 1 |  |
| `_canonical_bytes` | function | 8 | 0 | 3 |  |
| `ProductObservabilityBackendHealth` | value | 7 | 0 | 7 |  |
| `ProductObservabilityRuntimeState` | value | 6 | 0 | 28 |  |
| `_AuthorityBinding` | value | 5 | 0 | 3 |  |
| `PRODUCT_OBSERVABILITY_ENABLE_ENV` | constant | 3 | 0 | 3 |  |
| `PRODUCT_OBSERVABILITY_BACKEND_ENV` | constant | 3 | 0 | 2 |  |
| `PRODUCT_OBSERVABILITY_TOKEN_KEY_ENV` | constant | 3 | 0 | 2 |  |
| `PRODUCT_OBSERVABILITY_RUNTIME_VERSION` | constant | 3 | 0 | 5 |  |
| `ProductObservabilityRuntimeError` | exception | 2 | 0 | 36 |  |
| `PRODUCT_OBSERVABILITY_BACKEND_ID` | constant | 1 | 0 | 10 |  |

### `channels/web/live_voice_deployment_observer.py`（1,045 行；被 0 个生产文件导入；41 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `_StdlibDeploymentRuntimeTransport` | owner | 121 | 0 | 1 |  |
| `DeploymentRuntimeFacts` | value | 118 | 0 | 16 |  |
| `_facts_from_responses` | function | 73 | 0 | 2 |  |
| `observe_live_voice_deployment_runtime` | function | 68 | 0 | 1 |  |
| `LiveVoiceDeploymentObservationResult` | value | 66 | 0 | 8 |  |
| `_csp_status` | function | 60 | 0 | 2 |  |
| `_perform_request` | function | 49 | 0 | 1 |  |
| `_canonical_https` | function | 46 | 0 | 2 |  |
| `_fact_reasons` | function | 45 | 0 | 1 |  |
| `_validate_request` | function | 41 | 0 | 1 |  |
| `DeploymentRuntimeReason` | value | 29 | 0 | 39 |  |
| `_PinnedHTTPSConnection` | class | 27 | 0 | 1 |  |
| `_canonical_path` | function | 26 | 0 | 2 |  |
| `_resolve_private_address` | function | 20 | 0 | 1 |  |
| `_single_header` | function | 15 | 0 | 10 |  |
| `_hsts_valid` | function | 13 | 0 | 2 |  |
| `_csp_sources` | function | 12 | 0 | 1 |  |
| `_reason_for_transport_failure` | function | 12 | 0 | 1 |  |
| `LiveVoiceDeploymentObservationRequest` | value | 10 | 0 | 3 |  |
| `_ValidatedRequest` | value | 8 | 0 | 7 |  |
| `_tls_context` | function | 8 | 0 | 1 |  |
| `DeploymentRuntimeTlsVersion` | value | 7 | 0 | 25 |  |
| `_TransportFailure` | value | 7 | 0 | 14 |  |
| `_disabled_result` | function | 7 | 0 | 1 |  |
| `_closed_tls_version` | function | 6 | 0 | 1 |  |
| `_accept_value` | function | 5 | 0 | 1 |  |
| `_SafeHttpResponse` | value | 4 | 0 | 6 |  |
| `DeploymentRuntimeTransport` | value | 4 | 0 | 3 |  |
| `_comma_tokens` | function | 4 | 0 | 2 |  |
| `_TransportObservation` | value | 3 | 0 | 9 |  |
| `_MEDIA_SUBPROTOCOL` | constant | 1 | 0 | 2 |  |
| `_WEBSOCKET_KEY` | constant | 1 | 0 | 2 |  |
| `_WEBSOCKET_GUID` | constant | 1 | 0 | 1 |  |
| `_MAX_URL_UNITS` | constant | 1 | 0 | 2 |  |
| `_MAX_PATH_UNITS` | constant | 1 | 0 | 2 |  |
| `_MAX_CSP_UNITS` | constant | 1 | 0 | 2 |  |
| `_MIN_TIMEOUT_MS` | constant | 1 | 0 | 1 |  |
| `_MAX_TIMEOUT_MS` | constant | 1 | 0 | 1 |  |
| `_PATH_SEGMENT` | constant | 1 | 0 | 1 |  |
| `_DIRECTIVE_NAME` | constant | 1 | 0 | 1 |  |

### `server/live_voice/alpha_privacy_conformance.py`（1,025 行；被 0 个生产文件导入；56 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `evaluate_alpha_privacy_conformance` | function | 151 | 0 | 1 |  |
| `DeterministicAudioByteCanary` | value | 65 | 0 | 4 |  |
| `SyntheticSecretCanary` | value | 59 | 0 | 4 |  |
| `compute_alpha_privacy_capture_receipt` | function | 56 | 0 | 2 |  |
| `AlphaPrivacyConformancePlan` | value | 47 | 0 | 4 |  |
| `AlphaPrivacySurfaceObservation` | value | 43 | 0 | 4 |  |
| `AlphaPrivacyConformanceReport` | value | 39 | 0 | 5 |  |
| `_inspect_records` | function | 31 | 0 | 2 |  |
| `_record_findings` | function | 30 | 0 | 1 |  |
| `_inspect_chunks` | function | 29 | 0 | 2 |  |
| `_inspect_chunk` | function | 28 | 0 | 1 |  |
| `AlphaPrivacyCaptureRecord` | value | 28 | 0 | 14 |  |
| `_scan_record` | function | 28 | 0 | 1 |  |
| `AlphaPrivacySurface` | value | 22 | 0 | 23 |  |
| `_disabled_report` | function | 22 | 0 | 1 |  |
| `AlphaPrivacyCaptureRecordBuildResult` | value | 20 | 0 | 4 |  |
| `_inspect_record` | function | 19 | 0 | 1 |  |
| `build_alpha_privacy_capture_record` | function | 16 | 0 | 1 |  |
| `AlphaPrivacyRecordBuildReason` | value | 14 | 0 | 32 |  |
| `_patterns` | function | 12 | 0 | 5 |  |
| `SyntheticSecretKind` | value | 7 | 0 | 4 |  |
| `_run_ref` | function | 7 | 0 | 3 |  |
| `AlphaPrivacyCanaryFinding` | value | 7 | 0 | 6 |  |
| `AlphaPrivacyConformanceViolation` | exception | 6 | 0 | 25 |  |
| `CanaryRepresentation` | value | 6 | 0 | 17 |  |
| `_require_valid_records` | function | 6 | 0 | 2 |  |
| `AlphaPrivacyConformanceStatus` | value | 5 | 0 | 6 |  |
| `_ExactPattern` | value | 5 | 0 | 15 |  |
| `_RecordInspection` | value | 5 | 0 | 13 |  |
| `_RecordTupleInspection` | value | 5 | 0 | 8 |  |
| `_EXCLUDED_AUDIO_TRANSFORMATIONS` | constant | 5 | 0 | 1 |  |
| `AlphaPrivacyCaptureSource` | value | 4 | 0 | 10 |  |
| `_ChunkInspection` | value | 4 | 0 | 6 |  |
| `_encode_bounded_text_chunk` | function | 4 | 0 | 1 |  |
| `_hash_frame` | function | 4 | 0 | 10 |  |
| `_valid_chunk_payload` | function | 4 | 0 | 1 |  |
| `_ScanStats` | value | 4 | 0 | 1 |  |
| `AlphaPrivacyChunkKind` | value | 3 | 0 | 11 |  |
| `CanaryFamily` | value | 3 | 0 | 15 |  |
| `_HashUpdater` | value | 2 | 0 | 1 |  |

### `server/live_voice/observability_correlation_contract.py`（876 行；被 1 个生产文件导入；42 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ObservabilityCorrelationMap` | value | 179 | 1 | 8 | server/live_voice/product_observability_runtime.py |
| `_validated_map` | function | 97 | 0 | 3 |  |
| `evaluate_observability_correlation_replay` | function | 46 | 0 | 1 |  |
| `CorrelationTokenizationReceipt` | value | 44 | 1 | 7 | server/live_voice/product_observability_runtime.py |
| `CorrelationEvaluation` | value | 41 | 0 | 7 |  |
| `evaluate_observability_correlation_map` | function | 41 | 1 | 1 | server/live_voice/product_observability_runtime.py |
| `CorrelationReplayEvaluation` | value | 38 | 0 | 8 |  |
| `CorrelationCausationLink` | value | 33 | 1 | 5 | server/live_voice/product_observability_runtime.py |
| `_safe_public_token` | function | 25 | 0 | 5 |  |
| `_ALLOWED_CAUSATION_EDGES` | constant | 23 | 0 | 1 |  |
| `BoundedMetricDimensions` | value | 23 | 1 | 6 | server/live_voice/product_observability_runtime.py |
| `_IDENTITY_FIELD_BY_KIND` | constant | 20 | 0 | 5 |  |
| `HIGH_CARDINALITY_TRACE_FIELD_ORDER` | constant | 19 | 0 | 3 |  |
| `CorrelationIdentityKind` | value | 15 | 1 | 62 | server/live_voice/product_observability_runtime.py |
| `_optional_public_token` | function | 15 | 0 | 1 |  |
| `_METRIC_VALUES` | constant | 13 | 0 | 1 |  |
| `MetricDimension` | value | 13 | 1 | 5 | server/live_voice/product_observability_runtime.py |
| `_PUBLIC_TOKEN_KIND_BY_FIELD` | constant | 10 | 0 | 2 |  |
| `MetricDimensionKey` | value | 8 | 1 | 11 | server/live_voice/product_observability_runtime.py |
| `_correlation_token_set_digest` | function | 7 | 0 | 1 |  |
| `CorrelationReplayReason` | value | 6 | 0 | 10 |  |
| `CorrelationEvaluationReason` | value | 5 | 0 | 9 |  |
| `_looks_like_ordinary_pii` | function | 4 | 0 | 1 |  |
| `OBSERVABILITY_CORRELATION_CONTRACT_VERSION` | constant | 3 | 1 | 2 | server/live_voice/product_observability_runtime.py |
| `CORRELATION_TOKENIZATION_RECEIPT_VERSION` | constant | 3 | 1 | 2 | server/live_voice/product_observability_runtime.py |
| `CorrelationTokenizationReceiptVerifier` | constant | 3 | 0 | 1 |  |
| `CorrelationContractViolation` | exception | 2 | 0 | 34 |  |
| `PrivateCorrelationContent` | class | 2 | 0 | 4 |  |
| `CorrelationTokenizationIssuer` | value | 2 | 1 | 4 | server/live_voice/product_observability_runtime.py |
| `CorrelationTokenizationMethod` | value | 2 | 1 | 4 | server/live_voice/product_observability_runtime.py |
| `MAX_CORRELATION_IDENTITY_LENGTH` | constant | 1 | 0 | 2 |  |
| `MAX_CORRELATION_LINKS` | constant | 1 | 0 | 2 |  |
| `MAX_METRIC_DIMENSIONS` | constant | 1 | 0 | 2 |  |
| `MAX_SAFE_GENERATION` | constant | 1 | 0 | 1 |  |
| `PUBLIC_CORRELATION_TOKEN_VERSION` | constant | 1 | 0 | 1 |  |
| `PUBLIC_CORRELATION_TOKEN_DIGEST_LENGTH` | constant | 1 | 0 | 1 |  |
| `_PUBLIC_TOKEN` | constant | 1 | 0 | 1 |  |
| `_DIGEST` | constant | 1 | 0 | 1 |  |
| `_SCOPE_TAG` | constant | 1 | 0 | 1 |  |
| `_EMAIL` | constant | 1 | 0 | 1 |  |

### `server/live_voice/product_observability_adapter.py`（847 行；被 1 个生产文件导入；27 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProductObservabilityAdapter` | owner | 196 | 1 | 5 | server/live_voice/product_composition_registry.py |
| `activate_product_observability_adapter` | function | 119 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `ProductObservabilityLease` | owner | 69 | 0 | 8 |  |
| `ProductObservabilityActivationEvidence` | value | 32 | 1 | 3 | server/live_voice/product_composition_registry.py |
| `ProductObservabilityDisposition` | value | 27 | 0 | 8 |  |
| `ActiveProductObservabilityActivation` | value | 26 | 1 | 3 | server/live_voice/product_composition_registry.py |
| `_formal_observability_route_fact` | function | 25 | 0 | 1 |  |
| `_unavailable_after_failed_formalization` | function | 22 | 0 | 6 |  |
| `ProductObservabilityAdapterSnapshot` | value | 21 | 0 | 3 |  |
| `UnavailableProductObservabilityActivation` | value | 20 | 0 | 8 |  |
| `ProductObservabilityCloseResult` | value | 19 | 0 | 7 |  |
| `InactiveProductObservabilityActivation` | value | 18 | 0 | 3 |  |
| `_is_async_callable` | function | 14 | 0 | 2 |  |
| `ProductObservabilityReason` | value | 13 | 0 | 27 |  |
| `ProductObservabilityAdapterStats` | value | 13 | 0 | 4 |  |
| `ProductObservabilityActivationError` | exception | 12 | 1 | 4 | server/live_voice/product_composition_registry.py |
| `_package_only_route_fact` | function | 11 | 0 | 8 |  |
| `_close_timeout` | function | 11 | 0 | 1 |  |
| `_has_native_coroutine_code` | function | 10 | 0 | 2 |  |
| `ProductObservabilityLeaseState` | value | 7 | 0 | 23 |  |
| `_disabled_route_fact` | function | 7 | 0 | 2 |  |
| `ProductObservabilityLeaseCloseError` | exception | 6 | 0 | 2 |  |
| `_async_exporter` | function | 6 | 0 | 1 |  |
| `_route_fact_issuer` | function | 6 | 0 | 1 |  |
| `ProductObservabilityRouteFactIssuer` | constant | 3 | 0 | 3 |  |
| `ObservationExporter` | constant | 1 | 0 | 2 |  |
| `_CONSTRUCTION_TOKEN` | constant | 1 | 0 | 10 |  |

### `server/live_voice/observability_exporter.py`（734 行；被 4 个生产文件导入；29 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `LiveVoiceObservabilityExporterBuffer` | owner | 478 | 1 | 1 | server/live_voice/product_observability_adapter.py |
| `ExporterStats` | value | 47 | 0 | 5 |  |
| `ExporterSnapshot` | value | 21 | 1 | 6 | server/live_voice/product_observability_adapter.py |
| `_DeliveryHandshake` | class | 16 | 0 | 3 |  |
| `_positive_timeout` | function | 9 | 0 | 3 |  |
| `ExporterCloseTimeoutError` | exception | 6 | 1 | 2 | server/live_voice/product_observability_adapter.py |
| `mark_current_export_committed` | function | 6 | 0 | 1 |  |
| `AsyncLiveVoiceExporter` | value | 4 | 0 | 2 |  |
| `_BufferedRecord` | value | 4 | 0 | 7 |  |
| `_AttemptResult` | value | 4 | 0 | 8 |  |
| `_positive_integer` | function | 4 | 0 | 1 |  |
| `ExporterState` | constant | 3 | 0 | 4 |  |
| `FailureKind` | constant | 3 | 0 | 4 |  |
| `_CURRENT_DELIVERY_HANDSHAKE` | constant | 3 | 0 | 3 |  |
| `ObservabilityExporterError` | exception | 2 | 1 | 9 | server/live_voice/product_observability_adapter.py |
| `ExporterNotStartedError` | exception | 2 | 0 | 2 |  |
| `ExporterBackpressureError` | exception | 2 | 1 | 2 | server/live_voice/product_observability_adapter.py |
| `ExporterClosingError` | exception | 2 | 0 | 3 |  |
| `ExporterClosedError` | exception | 2 | 0 | 3 |  |
| `ExporterFailedError` | exception | 2 | 0 | 8 |  |
| `InvalidExportRecordError` | exception | 2 | 0 | 3 |  |
| `ReentrantExporterCloseError` | exception | 2 | 0 | 2 |  |
| `_InvalidAwaitableError` | exception | 2 | 0 | 2 |  |
| `DEFAULT_EXPORT_BUFFER_CAPACITY` | constant | 1 | 0 | 2 |  |
| `DEFAULT_EXPORT_TIMEOUT_SECONDS` | constant | 1 | 0 | 2 |  |
| `DEFAULT_CLOSE_TIMEOUT_SECONDS` | constant | 1 | 0 | 2 |  |
| `ExportRecord` | constant | 1 | 4 | 6 | server/live_voice/observability_fault_harness.py, server/live_voice/product_composition_registry.py, server/live_voice/product_observability_adapter.py |
| `ExportRecordKind` | constant | 1 | 0 | 4 |  |
| `ExporterCallback` | constant | 1 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts`（645 行；被 1 个生产文件导入；10 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `OrdinaryChromeL0BatchController` | class | 314 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx |
| `OrdinaryChromeBatchDependencies` | type | 15 | 0 | 2 |  |
| `parseOrdinaryChromeBatchConfig` | function | 14 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx |
| `OrdinaryChromeBatchProgress` | type | 9 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx |
| `OrdinaryChromeVoiceState` | type | 5 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx |
| `OrdinaryChromeVoiceControl` | type | 5 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx |
| `OrdinaryChromeBatchConfig` | type | 4 | 0 | 5 |  |
| `L0_ORDINARY_BATCH_QUERY_FLAG` | const | 1 | 0 | 1 |  |
| `L0_ORDINARY_BATCH_PORT_QUERY` | const | 1 | 0 | 1 |  |
| `L0_ORDINARY_BATCH_NONCE_QUERY` | const | 1 | 0 | 1 |  |

### `server/live_voice/observability_otel_codec.py`（641 行；被 1 个生产文件导入；30 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `OtelBackendRecord` | value | 129 | 1 | 7 | server/live_voice/product_observability_runtime.py |
| `encode_observation_for_otel_backend` | function | 72 | 1 | 2 | server/live_voice/product_observability_runtime.py |
| `encode_metric_for_otel_backend` | function | 59 | 1 | 2 | server/live_voice/product_observability_runtime.py |
| `validate_otel_backend_record` | function | 35 | 1 | 1 | server/live_voice/product_observability_runtime.py |
| `OtelBackendEncoding` | value | 32 | 0 | 7 |  |
| `OTEL_BACKEND_ROUTE_REQUIRED_ATTRIBUTES` | constant | 30 | 0 | 2 |  |
| `_COMMON_ATTRIBUTE_KEYS` | constant | 22 | 0 | 1 |  |
| `_record` | function | 21 | 0 | 2 |  |
| `OtelTraceContext` | value | 18 | 1 | 4 | server/live_voice/product_observability_runtime.py |
| `_binding_attributes` | function | 14 | 0 | 2 |  |
| `_closed_attribute` | function | 13 | 0 | 2 |  |
| `_route_attributes` | function | 11 | 0 | 2 |  |
| `_decoded_payload` | function | 10 | 0 | 1 |  |
| `OTEL_SPAN_REQUIRED_ATTRIBUTES` | constant | 9 | 0 | 2 |  |
| `_attributes` | function | 9 | 0 | 2 |  |
| `_checked_trace` | function | 9 | 0 | 1 |  |
| `_canonical_bytes` | function | 8 | 1 | 3 | server/live_voice/product_observability_runtime.py |
| `_SPAN_ONLY_ATTRIBUTE_KEYS` | constant | 7 | 0 | 2 |  |
| `OTEL_METRIC_REQUIRED_ATTRIBUTES` | constant | 7 | 0 | 2 |  |
| `OtelBackendCodecReason` | value | 7 | 0 | 20 |  |
| `_validate_trace_id` | function | 6 | 0 | 6 |  |
| `_rejection` | function | 6 | 0 | 13 |  |
| `OtelBackendSignalKind` | value | 3 | 1 | 14 | server/live_voice/product_observability_runtime.py |
| `_digest` | function | 2 | 0 | 3 |  |
| `_source_fingerprint` | function | 2 | 0 | 1 |  |
| `OTEL_BACKEND_SCHEMA_VERSION` | constant | 1 | 0 | 4 |  |
| `_TRACE_ID` | constant | 1 | 0 | 2 |  |
| `_SPAN_ID` | constant | 1 | 0 | 4 |  |
| `_SHA256` | constant | 1 | 0 | 2 |  |
| `OTEL_BACKEND_ATTRIBUTE_KEYS` | constant | 1 | 0 | 3 |  |

### `server/live_voice/alpha_benchmark.py`（633 行；被 0 个生产文件导入；23 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `run_alpha_benchmark` | function | 111 | 0 | 1 |  |
| `build_alpha_benchmark_report` | function | 82 | 0 | 1 |  |
| `_evaluate_target` | function | 60 | 0 | 1 |  |
| `AlphaBenchmarkPlan` | value | 54 | 0 | 5 |  |
| `_evaluate_executed_target` | function | 47 | 0 | 1 |  |
| `AlphaBenchmarkTarget` | value | 41 | 0 | 7 |  |
| `_plan_sha256` | function | 25 | 0 | 2 |  |
| `AlphaBenchmarkCase` | value | 16 | 0 | 2 |  |
| `_positive_finite` | function | 14 | 0 | 2 |  |
| `AlphaBenchmarkReport` | value | 13 | 0 | 7 |  |
| `AlphaBenchmarkTargetResult` | value | 12 | 0 | 6 |  |
| `AlphaBenchmarkTargetReason` | value | 9 | 0 | 23 |  |
| `_nonnegative_safe_integer` | function | 7 | 0 | 1 |  |
| `AlphaBenchmarkSample` | value | 7 | 0 | 5 |  |
| `_same_route` | function | 7 | 0 | 3 |  |
| `_target_route_key` | function | 7 | 0 | 1 |  |
| `AlphaBenchmarkViolation` | exception | 6 | 0 | 33 |  |
| `_safe_label` | function | 6 | 0 | 7 |  |
| `_positive_safe_integer` | function | 6 | 0 | 1 |  |
| `_percentile` | function | 6 | 0 | 4 |  |
| `AlphaBenchmarkExecution` | value | 4 | 0 | 4 |  |
| `_CANDIDATE_SHA` | constant | 1 | 0 | 1 |  |
| `_SAFE_LABEL` | constant | 1 | 0 | 1 |  |

### `channels/web/live_voice_deployment_preflight.py`（449 行；被 1 个生产文件导入；19 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `evaluate_live_voice_deployment_preflight` | function | 122 | 1 | 1 | channels/web/live_voice_deployment_observer.py |
| `DeploymentPreflightResult` | value | 37 | 0 | 4 |  |
| `_csp_allows_websocket` | function | 33 | 0 | 1 |  |
| `DeploymentPreflightReason` | value | 31 | 1 | 36 | channels/web/live_voice_deployment_observer.py |
| `_validated_host` | function | 30 | 0 | 2 |  |
| `_validate_allowed_origins` | function | 23 | 0 | 1 |  |
| `_parse_origin` | function | 22 | 0 | 2 |  |
| `_parse_websocket` | function | 21 | 0 | 2 |  |
| `DeploymentPreflightFacts` | value | 17 | 1 | 2 | channels/web/live_voice_deployment_observer.py |
| `_result` | function | 12 | 0 | 4 |  |
| `_safe_ascii` | function | 8 | 0 | 3 |  |
| `_websocket_matches_origin` | function | 7 | 0 | 2 |  |
| `TlsTerminationFact` | value | 6 | 1 | 7 | channels/web/live_voice_deployment_observer.py |
| `_Origin` | value | 5 | 0 | 5 |  |
| `_WebSocketEndpoint` | value | 4 | 0 | 4 |  |
| `_owner_label_valid` | function | 2 | 0 | 1 |  |
| `_DOMAIN_LABEL` | constant | 1 | 1 | 1 | channels/web/live_voice_deployment_observer.py |
| `_OWNER_LABEL` | constant | 1 | 0 | 1 |  |
| `_CSP_BROAD_SOURCES` | constant | 1 | 0 | 1 |  |

### `server/live_voice/observability_fault_harness.py`（391 行；被 0 个生产文件导入；17 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `LiveVoiceObservabilityFaultHarness` | owner | 187 | 0 | 4 |  |
| `ObservabilityFaultHarnessSnapshot` | value | 31 | 0 | 5 |  |
| `DisabledObservabilityFaultHarness` | owner | 23 | 0 | 3 |  |
| `create_observability_fault_harness` | function | 21 | 0 | 2 |  |
| `_Attempt` | value | 13 | 0 | 2 |  |
| `ObservabilityFaultOutcome` | value | 7 | 0 | 13 |  |
| `ObservabilityFaultHarnessState` | value | 7 | 0 | 6 |  |
| `ObservabilityFaultAttemptSnapshot` | value | 7 | 0 | 4 |  |
| `ObservabilityFaultAction` | value | 6 | 0 | 11 |  |
| `_StallControl` | value | 3 | 0 | 2 |  |
| `ObservabilityFaultHarnessError` | exception | 2 | 0 | 3 |  |
| `InjectedObservabilityExportError` | exception | 2 | 0 | 2 |  |
| `ObservabilityFaultScriptExhaustedError` | exception | 2 | 0 | 2 |  |
| `MAX_OBSERVABILITY_FAULT_STEPS` | constant | 1 | 0 | 4 |  |
| `ObservabilityFaultRecordKind` | constant | 1 | 0 | 4 |  |
| `_CONSTRUCTION_TOKEN` | constant | 1 | 0 | 2 |  |
| `_DISABLED_HARNESS` | constant | 1 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/formal/l0Measurement.ts`（390 行；被 2 个生产文件导入；13 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `recordBrowserL0Milestone` | function | 85 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `registerBrowserL0Response` | function | 18 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `BrowserL0Milestone` | type | 14 | 0 | 3 |  |
| `BrowserL0Binding` | type | 12 | 1 | 6 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `BrowserL0Envelope` | type | 12 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts |
| `BrowserL0RunLabels` | type | 7 | 1 | 10 | channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts |
| `BrowserL0ControlSnapshot` | type | 7 | 1 | 2 | channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts |
| `BrowserL0Control` | type | 6 | 1 | 4 | channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts |
| `browserL0Enabled` | function | 3 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `browserL0Available` | function | 3 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts |
| `browserL0Control` | function | 3 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts |
| `L0_MEASUREMENT_ENVELOPE_VERSION` | const | 1 | 0 | 2 |  |
| `L0_BROWSER_QUERY_FLAG` | const | 1 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/formal/audioDiagnostics.ts`（371 行；被 7 个生产文件导入；9 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `profileAudioOperation` | function | 60 | 2 | 0 | channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts, channels/web/frontend/src/services/webClient.ts |
| `recordAudioDiagnostic` | function | 53 | 5 | 6 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx, channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts, channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts |
| `audioDiagnosticBundle` | function | 40 | 0 | 2 |  |
| `diagnosticIdentity` | function | 19 | 1 | 1 | channels/web/frontend/src/services/webClient.ts |
| `downloadAudioDiagnostics` | function | 17 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx |
| `AudioDiagnostic` | type | 8 | 0 | 6 |  |
| `markAudioRpcRejection` | function | 7 | 1 | 0 | channels/web/frontend/src/services/webClient.ts |
| `clearAudioDiagnostics` | function | 7 | 0 | 1 |  |
| `audioDiagnosticSnapshot` | function | 5 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/formal/webPlatformDiagnostics.ts`（326 行；被 1 个生产文件导入；13 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `WebPlatformDiagnosticsMonitor` | class | 123 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `collectWebPlatformDiagnostics` | function | 52 | 0 | 1 |  |
| `WebPlatformDiagnosticsSnapshot` | type | 18 | 1 | 6 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `WebPlatformDiagnosticsEnvironment` | type | 14 | 0 | 5 |  |
| `DiagnosticsMediaDeviceLike` | type | 5 | 0 | 1 |  |
| `DiagnosticsEventTargetLike` | type | 4 | 0 | 6 |  |
| `DiagnosticsDocumentLike` | type | 4 | 0 | 2 |  |
| `MicrophonePermissionStatusLike` | type | 3 | 0 | 4 |  |
| `DiagnosticsMediaDevicesLike` | type | 3 | 0 | 2 |  |
| `MicrophonePermissionFact` | type | 1 | 0 | 3 |  |
| `DeviceAvailabilityFact` | type | 1 | 0 | 4 |  |
| `UserActivationFact` | type | 1 | 0 | 1 |  |
| `BrowserEvidenceFamily` | type | 1 | 0 | 2 |  |

### `server/runtime/agent_adapter/formal_model_diagnostics.py`（320 行；被 1 个生产文件导入；8 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `FormalModelDiagnostics` | class | 209 | 0 | 1 |  |
| `TaskModelTiming` | class | 49 | 0 | 2 |  |
| `observe_private_task_model` | function | 14 | 1 | 0 | server/runtime/agent_adapter/interface_deep.py |
| `observe_formal_model` | function | 10 | 1 | 0 | server/runtime/agent_adapter/interface_deep.py |
| `_get` | function | 6 | 1 | 4 | server/runtime/agent_adapter/interface_deep.py |
| `_MAX_CALLS` | constant | 1 | 0 | 2 |  |
| `_MAX_MESSAGES` | constant | 1 | 0 | 2 |  |
| `_MAX_TEXT` | constant | 1 | 0 | 4 |  |

### `channels/web/frontend/src/features/live-voice/formal/liveVoiceRouteTelemetry.ts`（257 行；被 3 个生产文件导入；9 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `createRouteTelemetryRecord` | function | 46 | 2 | 1 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts, channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts |
| `createRouteTelemetryLedger` | function | 33 | 0 | 0 |  |
| `RouteTelemetryInput` | type | 10 | 0 | 3 |  |
| `RouteTelemetryRecord` | type | 10 | 3 | 8 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts, channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts, channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts |
| `RouteTelemetryViolation` | class | 9 | 0 | 3 |  |
| `RouteTelemetryLedger` | type | 7 | 0 | 1 |  |
| `ROUTE_CLASSES` | const | 1 | 0 | 3 |  |
| `RouteImplementationClass` | type | 1 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts |
| `CONTRACT_VERSION` | const | 1 | 3 | 1 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts, channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts, channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts |

### `common/live_voice_profiling.py`（226 行；被 20 个生产文件导入；11 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `ProfileSpan` | class | 67 | 3 | 2 | server/live_voice/task_semantics.py, server/runtime/agent_adapter/formal_model_diagnostics.py, server/runtime/agent_adapter/interface_deep.py |
| `profiled` | function | 35 | 10 | 0 | gateway/live_voice/product_streaming_synthesis.py, gateway/live_voice/streaming_speech_route.py, gateway/live_voice/streaming_synthesis_route.py |
| `identity_fields` | function | 26 | 7 | 2 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/agent_bridge_runtime.py, server/live_voice/latency_measurement.py |
| `error_fields` | function | 23 | 3 | 1 | server/live_voice/native_business_router.py, server/live_voice/openai_streaming_speech.py, server/runtime/agent_adapter/formal_model_diagnostics.py |
| `profile_tool_event` | function | 19 | 2 | 0 | server/live_voice/project_code_executor.py, server/runtime/agent_adapter/interface_deep.py |
| `_IDS` | constant | 7 | 1 | 2 | common/live_voice_audio_diagnostics.py |
| `profile_snapshot_event` | function | 6 | 3 | 0 | server/live_voice/openai_realtime_native_engine.py, server/live_voice/openai_realtime_session.py, server/runtime/agent_adapter/formal_model_diagnostics.py |
| `profile_event` | function | 5 | 7 | 2 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/agent_bridge_runtime.py, server/live_voice/latency_measurement.py |
| `current_profile_fields` | function | 2 | 2 | 0 | common/live_voice_audio_diagnostics.py, server/runtime/agent_adapter/formal_model_diagnostics.py |
| `_CURRENT` | constant | 1 | 0 | 7 |  |
| `_CONTAINERS` | constant | 1 | 0 | 1 |  |

### `server/live_voice/speech_socket_diagnostics.py`（210 行；被 1 个生产文件导入；4 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SocketDiagnostics` | class | 109 | 0 | 1 |  |
| `_ObservedFlowControl` | class | 43 | 0 | 5 |  |
| `attach_socket_diagnostics` | function | 23 | 1 | 0 | server/live_voice/openai_streaming_speech.py |
| `diagnostic_socket_factory` | function | 13 | 1 | 0 | server/live_voice/openai_streaming_speech.py |

### `common/live_voice_audio_diagnostics.py`（182 行；被 9 个生产文件导入；21 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `record_audio_diagnostic` | function | 36 | 9 | 0 | common/live_voice_profiling.py, gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/dedicated_media_route.py |
| `_VALUES` | constant | 24 | 0 | 3 |  |
| `_encode_record` | function | 23 | 0 | 1 |  |
| `FAILURE_CODES` | constant | 23 | 1 | 1 | server/live_voice/openai_streaming_speech.py |
| `_LABELS` | constant | 18 | 0 | 2 |  |
| `WIRE_EVENTS` | constant | 10 | 1 | 1 | server/live_voice/openai_streaming_speech.py |
| `_run` | function | 9 | 1 | 1 | gateway/live_voice/dedicated_media_registration.py |
| `_LOGGER` | constant | 1 | 3 | 1 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/streaming_speech_route.py, server/live_voice/openai_streaming_speech.py |
| `_QUEUE` | constant | 1 | 0 | 3 |  |
| `_START_LOCK` | constant | 1 | 0 | 1 |  |
| `_WORKER` | constant | 1 | 0 | 5 |  |
| `_DROPPED` | constant | 1 | 0 | 3 |  |
| `_CLOCK_ID` | constant | 1 | 0 | 1 |  |
| `_SEQUENCE` | constant | 1 | 0 | 2 |  |
| `_JSON_TOKEN` | constant | 1 | 0 | 1 |  |
| `_IDS` | constant | 1 | 1 | 7 | common/live_voice_profiling.py |
| `_IDS` | constant | 1 | 1 | 7 | common/live_voice_profiling.py |
| `_IDS` | constant | 1 | 1 | 7 | common/live_voice_profiling.py |
| `_IDS` | constant | 1 | 1 | 7 | common/live_voice_profiling.py |
| `_TOKENS` | constant | 1 | 0 | 1 |  |
| `_VALUES` | constant | 1 | 0 | 3 |  |

### `channels/web/frontend/src/features/live-voice/formal/audioDiagnosticJournal.ts`（109 行；被 1 个生产文件导入；4 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `clearAudioDiagnosticJournal` | function | 15 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/audioDiagnostics.ts |
| `flushAudioDiagnosticJournal` | function | 10 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/audioDiagnostics.ts |
| `appendAudioDiagnosticJournal` | function | 7 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/audioDiagnostics.ts |
| `readAudioDiagnosticJournal` | function | 7 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/audioDiagnostics.ts |

### `channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx`（105 行；被 1 个生产文件导入；1 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `L0OrdinaryChromeBatchPanel` | function | 85 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/index.tsx |

### `server/live_voice/speech_http_diagnostics.py`（63 行；被 2 个生产文件导入；2 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SpeechHttpDiagnostics` | class | 49 | 2 | 0 | server/live_voice/batch_speech.py, server/live_voice/openai_streaming_speech.py |
| `_PHASES` | constant | 5 | 0 | 1 |  |

## 16 Schema/protocol（5 文件，6,958 行）

### `common/schema/live_voice_contract_v2.py`（4,000 行；被 63 个生产文件导入；120 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `EventSequenceTracker` | class | 508 | 1 | 1 | server/live_voice/agent_bridge_runtime.py |
| `_command_payload` | function | 222 | 0 | 1 |  |
| `IdentityRegistry` | owner | 195 | 0 | 9 |  |
| `EventEnvelope` | value | 186 | 6 | 13 | server/live_voice/agent_bridge_runtime.py, server/live_voice/agent_conversation_runtime.py, server/live_voice/jiuwenswarm_agent_adapter.py |
| `ResultEnvelope` | value | 177 | 7 | 15 | server/live_voice/formal_task_models.py, server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py |
| `WorkProgressEventV2` | value | 156 | 5 | 6 | server/live_voice/agent_bridge_runtime.py, server/live_voice/agent_conversation_runtime.py, server/live_voice/persistent_task_core.py |
| `CommandEnvelope` | value | 140 | 9 | 20 | server/live_voice/agent_conversation_runtime.py, server/live_voice/formal_task_models.py, server/live_voice/jiuwenswarm_round_harness.py |
| `CapabilityDescriptor` | value | 121 | 1 | 4 | server/live_voice/batch_speech.py |
| `QueryEnvelope` | value | 108 | 4 | 7 | server/live_voice/p3_authenticated_composition.py, server/live_voice/persistent_task_core.py, server/live_voice/product_p3_text_adapter.py |
| `_validate_event_payload` | function | 97 | 0 | 1 |  |
| `TurnCommit` | value | 88 | 20 | 8 | server/live_voice/agent_bridge.py, server/live_voice/agent_bridge_runtime.py, server/live_voice/agent_conversation_runtime.py |
| `TurnCommitLedger` | owner | 84 | 6 | 3 | server/agent_ws_server.py, server/live_voice/conversation_runtime.py, server/live_voice/p3_authenticated_composition.py |
| `_result_extensions` | function | 72 | 0 | 3 |  |
| `_EVENT_RULES` | constant | 72 | 0 | 6 |  |
| `ContextRef` | value | 70 | 8 | 11 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_business_context.py, server/live_voice/native_interaction_runtime.py |
| `ResponseFence` | owner | 64 | 3 | 1 | server/live_voice/conversation_runtime.py, server/live_voice/conversation_runtime_loop.py, server/live_voice/speech_ports.py |
| `CommandResultLedger` | owner | 64 | 0 | 1 |  |
| `_freeze_json` | function | 58 | 0 | 4 |  |
| `WorkProgressSource` | value | 54 | 1 | 4 | server/live_voice/agent_bridge_runtime.py |
| `ContractError` | value | 45 | 1 | 13 | server/live_voice/batch_speech.py |
| `_LIFECYCLE_TRANSITIONS` | constant | 43 | 0 | 1 |  |
| `ContextRevision` | value | 39 | 0 | 4 |  |
| `_constraint_list` | function | 38 | 0 | 2 |  |
| `CapabilityRegistry` | owner | 36 | 0 | 1 |  |
| `ContextRedaction` | value | 34 | 0 | 4 |  |
| `OriginRef` | value | 32 | 4 | 6 | server/live_voice/formal_task_models.py, server/live_voice/p3_production_intent_composition.py, server/live_voice/product_composition_registry.py |
| `ContractViolation` | exception | 29 | 9 | 5 | server/live_voice/formal_task_models.py, server/live_voice/p3_production_intent_composition.py, server/live_voice/persistent_task_core.py |
| `validate_transition` | function | 29 | 4 | 2 | server/live_voice/conversation_runtime.py, server/live_voice/task_core.py, server/live_voice/task_event_subscription.py |
| `_canonical_number` | function | 28 | 0 | 1 |  |
| `ScopeRef` | value | 28 | 39 | 24 | server/live_voice/agent_bridge_runtime.py, server/live_voice/agent_conversation_runtime.py, server/live_voice/batch_speech.py |
| `ConnectionEpochRef` | value | 26 | 0 | 6 |  |
| `ProducerRef` | value | 25 | 4 | 4 | server/live_voice/product_composition_registry.py, server/live_voice/product_p3_text_adapter.py, server/live_voice/progress_notification_arbiter.py |
| `IdentityRef` | value | 23 | 2 | 22 | server/live_voice/progress_notification_arbiter.py, server/live_voice/task_progress_return.py |
| `_canonical_frozen` | function | 22 | 0 | 3 |  |
| `parse_v2_envelope` | function | 22 | 0 | 1 |  |
| `_require_exact_keys` | function | 20 | 0 | 32 |  |
| `_query_payload` | function | 20 | 0 | 1 |  |
| `_context_uri` | function | 18 | 0 | 1 |  |
| `_COMMAND_TARGETS` | constant | 18 | 0 | 2 |  |
| `_COMMAND_DISPOSITION_ERROR_CODES` | constant | 18 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/formal/liveVoiceContractV2.ts`（2,785 行；被 2 个生产文件导入；81 个顶层 symbol，其中 13 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `EventSequenceTracker` | class | 370 | 0 | 0 |  |
| `IdentityRegistry` | class | 106 | 0 | 9 |  |
| `parseEventEnvelope` | function | 83 | 2 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx, channels/web/frontend/src/features/live-voice/formal/productTextProgress.ts |
| `parseCommandEnvelope` | function | 72 | 0 | 7 |  |
| `parseWorkProgressEventV2` | function | 60 | 0 | 4 |  |
| `parseQueryEnvelope` | function | 51 | 0 | 3 |  |
| `ResponseFence` | class | 48 | 0 | 0 |  |
| `CommandResultLedger` | class | 45 | 0 | 0 |  |
| `parseResultEnvelope` | function | 36 | 0 | 5 |  |
| `parseCapabilityDescriptor` | function | 36 | 0 | 1 |  |
| `TurnCommitLedger` | class | 36 | 0 | 2 |  |
| `parseTurnCommit` | function | 30 | 0 | 2 |  |
| `buildTaskUnreadEventsAck` | function | 28 | 0 | 0 |  |
| `CapabilityRegistry` | class | 24 | 0 | 0 |  |
| `parseV2Envelope` | function | 21 | 0 | 0 |  |
| `parseContextRef` | function | 20 | 0 | 2 |  |
| `validateTransition` | function | 17 | 0 | 1 |  |
| `canonicalJson` | function | 16 | 1 | 20 | channels/web/frontend/src/features/live-voice/formal/productTextProgress.ts |
| `TaskUnreadEvent` | type | 16 | 0 | 2 |  |
| `ErrorCode` | type | 15 | 0 | 10 |  |
| `EventEnvelope` | type | 15 | 0 | 14 |  |
| `dispatchCancel` | function | 15 | 0 | 0 |  |
| `parseTaskUnreadEventsResult` | function | 14 | 0 | 1 |  |
| `IdentityKind` | type | 13 | 0 | 11 |  |
| `CapabilityDescriptor` | type | 13 | 0 | 3 |  |
| `parseContractError` | function | 12 | 0 | 1 |  |
| `WorkProgressEventV2` | type | 12 | 0 | 1 |  |
| `ContextRef` | type | 11 | 0 | 6 |  |
| `TurnCommit` | type | 11 | 0 | 7 |  |
| `EventApplyStatus` | type | 11 | 0 | 3 |  |
| `parseScopeRef` | function | 10 | 0 | 9 |  |
| `ResultEnvelope` | type | 10 | 0 | 14 |  |
| `TaskUnreadEventsPage` | type | 10 | 0 | 2 |  |
| `ContractViolation` | class | 9 | 0 | 5 |  |
| `parseIdentityRef` | function | 9 | 0 | 9 |  |
| `ContractErrorValue` | type | 8 | 0 | 11 |  |
| `parseConnectionEpochRef` | function | 8 | 0 | 1 |  |
| `TaskUnreadEventsAckSeed` | type | 8 | 0 | 1 |  |
| `dispatchCommittedInput` | function | 8 | 0 | 0 |  |
| `contractError` | function | 7 | 0 | 9 |  |

### `gateway/live_voice/speech_rpc.py`（142 行；被 1 个生产文件导入；5 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `register_speech_rpc_handlers` | function | 118 | 1 | 0 | gateway/channel_manager/web/app_web_handlers.py |
| `CAPABILITIES_METHOD` | constant | 1 | 0 | 1 |  |
| `RECOGNIZE_BATCH_METHOD` | constant | 1 | 0 | 1 |  |
| `SYNTHESIZE_BATCH_METHOD` | constant | 1 | 0 | 1 |  |
| `CANCEL_METHOD` | constant | 1 | 0 | 1 |  |

### `common/live_voice_operation_budgets.py`（21 行；被 4 个生产文件导入；7 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SEMANTIC_MODEL_TIMEOUT_SECONDS` | constant | 1 | 1 | 0 | server/live_voice/task_semantics.py |
| `SEMANTIC_ANALYSIS_RECOVERY_TIMEOUT_SECONDS` | constant | 1 | 0 | 0 |  |
| `SEMANTIC_INPUT_TIMEOUT_SECONDS` | constant | 1 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `SEMANTIC_TRANSPORT_TIMEOUT_SECONDS` | constant | 1 | 0 | 1 |  |
| `NATIVE_AGENT_TIMEOUT_SECONDS` | constant | 1 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `NATIVE_AGENT_MAX_TIMEOUT_SECONDS` | constant | 1 | 1 | 0 | server/live_voice/agent_conversation_runtime.py |
| `NATIVE_DELEGATE_TRANSPORT_TIMEOUT_SECONDS` | constant | 1 | 1 | 0 | gateway/live_voice/native_interaction_runtime_client.py |

### `common/live_voice_capture_limits.py`（10 行；被 3 个生产文件导入；2 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `MAX_CAPTURE_DURATION_SECONDS` | constant | 1 | 1 | 0 | gateway/live_voice/streaming_speech_route.py |
| `MAX_CAPTURE_WAV_BYTES` | constant | 1 | 2 | 0 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/batch_speech.py |

## 17 Legacy/compat（9 文件，3,096 行）

### `channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts`（873 行；被 1 个生产文件导入；2 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `useLiveVoiceDemo` | function | 725 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/index.tsx |
| `UseLiveVoiceDemoOptions` | type | 15 | 0 | 1 |  |

### `channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx`（637 行；被 2 个生产文件导入；11 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `LiveVoiceDemoBar` | function | 230 | 2 | 2 | channels/web/frontend/src/components/ChatPanel/index.tsx, channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `LiveVoiceDemoBarProps` | type | 38 | 2 | 4 | channels/web/frontend/src/components/ChatPanel/index.tsx, channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `FormalProductLiveVoiceDemoBar` | function | 36 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/index.tsx |
| `formalProductVoiceActivity` | function | 23 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/index.tsx |
| `LiveVoiceCommandCenterProps` | type | 19 | 0 | 2 |  |
| `FormalProductTaskPresentationState` | type | 18 | 0 | 1 |  |
| `productVoiceInputAvailableAfterReplyFailure` | function | 4 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/index.tsx |
| `FormalProductLiveVoiceDemoBarProps` | type | 3 | 0 | 1 |  |
| `LiveVoiceVisualState` | type | 1 | 0 | 5 |  |
| `LiveVoiceCommandRoute` | type | 1 | 0 | 2 |  |
| `LiveVoiceTaskOperation` | type | 1 | 0 | 3 |  |

### `channels/web/frontend/src/features/live-voice/liveVoiceCore.ts`（445 行；被 2 个生产文件导入；12 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `LiveVoiceCore` | type | 15 | 1 | 2 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `LiveVoiceSnapshot` | type | 10 | 1 | 5 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `FinalTranscriptResult` | type | 7 | 0 | 2 |  |
| `LiveVoiceSpeechCallbacks` | type | 5 | 0 | 1 |  |
| `SpeechEnqueueResult` | type | 5 | 0 | 2 |  |
| `LiveVoiceError` | type | 4 | 0 | 2 |  |
| `LiveVoiceSpeechPlayer` | type | 4 | 2 | 2 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts, channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `LiveVoiceCoreOptions` | type | 4 | 0 | 2 |  |
| `createLiveVoiceCore` | function | 3 | 1 | 0 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `LiveVoiceStatus` | type | 1 | 0 | 2 |  |
| `FinalTranscriptRejection` | type | 1 | 0 | 1 |  |
| `SpeechEnqueueRejection` | type | 1 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/liveVoiceStreamingSpeech.ts`（321 行；被 1 个生产文件导入；10 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `advanceLiveVoiceStreamingSpeech` | function | 85 | 1 | 0 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `createLiveVoiceStreamingSpeechState` | function | 12 | 1 | 1 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `LiveVoiceStreamingSpeechState` | type | 10 | 0 | 7 |  |
| `LiveVoiceStreamingSpeechFallbackReason` | type | 7 | 0 | 2 |  |
| `LiveVoiceStreamingSpeechObservation` | type | 6 | 0 | 3 |  |
| `LiveVoiceStreamingSpeechEmission` | type | 5 | 0 | 3 |  |
| `LiveVoiceStreamingSpeechResult` | type | 5 | 0 | 3 |  |
| `LiveVoiceStreamingSpeechPhase` | type | 1 | 0 | 1 |  |
| `LiveVoiceStreamingSpeechMode` | type | 1 | 0 | 1 |  |
| `LiveVoiceStreamingSpeechOutcome` | type | 1 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/liveVoiceTurnLifecycle.ts`（256 行；被 1 个生产文件导入；15 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `selectLiveVoiceStreamingFinalTimeoutAction` | function | 38 | 1 | 0 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `resolveLiveVoiceSessionTransition` | function | 33 | 1 | 0 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `selectLiveVoicePostSpeechAction` | function | 32 | 1 | 0 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `resolveLiveVoiceTurnOriginatingSessionId` | function | 17 | 1 | 0 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `LiveVoiceStreamingFinalTimeoutInput` | type | 16 | 0 | 1 |  |
| `LiveVoicePostSpeechInput` | type | 13 | 0 | 1 |  |
| `shouldResumeAfterSilentResponse` | function | 9 | 1 | 0 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `LiveVoiceSessionTransitionInput` | type | 8 | 0 | 1 |  |
| `SilentResponseResumeInput` | type | 7 | 0 | 1 |  |
| `LiveVoiceTurnSessionRebindInput` | type | 6 | 0 | 1 |  |
| `LiveVoiceSessionTransitionResult` | type | 4 | 0 | 1 |  |
| `LiveVoiceSessionTransitionAction` | type | 1 | 0 | 2 |  |
| `LiveVoicePostSpeechAction` | type | 1 | 0 | 1 |  |
| `LIVE_VOICE_STREAMING_FINAL_TIMEOUT_MS` | const | 1 | 1 | 0 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `LiveVoiceStreamingFinalTimeoutAction` | type | 1 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechSynthesisAdapter.ts`（178 行；被 1 个生产文件导入；6 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `BrowserSpeechSynthesisAdapter` | class | 94 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts |
| `BrowserSpeechSynthesisAdapterViolation` | class | 9 | 1 | 9 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts |
| `BrowserSynthesisCapability` | type | 7 | 0 | 1 |  |
| `BrowserSynthesisEnvironment` | type | 7 | 1 | 3 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts |
| `BrowserSynthesisCallbacks` | type | 5 | 0 | 1 |  |
| `BrowserSynthesisRequest` | type | 4 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts`（150 行；被 1 个生产文件导入；3 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `createIntegratedP1Route` | function | 104 | 1 | 0 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `IntegratedP1Route` | type | 15 | 1 | 1 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `IntegratedP1RouteOptions` | type | 6 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/liveVoiceMessageGate.ts`（119 行；被 1 个生产文件导入；3 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `selectLiveVoiceResponseMessages` | function | 52 | 1 | 0 | channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts |
| `LiveVoiceMessageGateResult` | type | 14 | 0 | 1 |  |
| `SelectLiveVoiceResponseMessagesOptions` | type | 11 | 0 | 1 |  |

### `channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechRecognitionAdapter.ts`（117 行；被 1 个生产文件导入；5 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `BrowserSpeechRecognitionAdapter` | class | 69 | 1 | 0 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts |
| `BrowserRecognitionObservation` | type | 10 | 1 | 1 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts |
| `BrowserSpeechRecognitionAdapterViolation` | class | 9 | 1 | 5 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts |
| `BrowserRecognitionCapability` | type | 8 | 0 | 1 |  |
| `BrowserRecognitionCapture` | type | 4 | 1 | 7 | channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts |

## ?? unassigned（2 文件，120 行）

### `channels/web/frontend/src/features/live-voice/formal/nativeWorkState.ts`（66 行；被 2 个生产文件导入；9 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `parseNativeWorkStateNotification` | function | 23 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `nativeWorkSnapshotAdvances` | function | 9 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `nativeWorkBindingMatches` | function | 4 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `NativeWorkObservation` | type | 3 | 0 | 1 |  |
| `NativeWorkStateSnapshot` | type | 3 | 2 | 4 | channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx, channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `NATIVE_WORK_STATE_VERSION` | const | 1 | 0 | 1 |  |
| `NATIVE_WORK_STATES` | const | 1 | 1 | 2 | channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx |
| `NativeWorkPhase` | type | 1 | 0 | 3 |  |
| `NativeWorkStateNotification` | type | 1 | 1 | 1 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |

### `channels/web/frontend/src/features/live-voice/formal/nativeGeneratedText.ts`（54 行；被 2 个生产文件导入；3 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `parseNativeGeneratedText` | function | 32 | 1 | 0 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |
| `nativeVoiceResponseKey` | function | 6 | 1 | 0 | channels/web/frontend/src/stores/chatStore.ts |
| `NativeGeneratedMessage` | type | 4 | 1 | 3 | channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx |

## NATIVE (excluded)（19 文件，13,231 行）

### `server/live_voice/openai_realtime_native_engine.py`（3,839 行；被 5 个生产文件导入；47 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `OpenAIRealtimeNativeInteractionEngine` | owner | 3067 | 2 | 0 | gateway/channel_manager/web/app_web_handlers.py, gateway/live_voice/dedicated_media_registration.py |
| `_response_envelope` | function | 88 | 0 | 3 |  |
| `_session_update` | function | 71 | 0 | 1 |  |
| `_EVENT_KEYS` | constant | 70 | 0 | 1 |  |
| `_business_argument_shape` | function | 39 | 0 | 1 |  |
| `NativeInputAudioFrame` | value | 29 | 1 | 3 | gateway/live_voice/dedicated_media_registration.py |
| `_closed_event` | function | 29 | 0 | 1 |  |
| `_response_ref` | function | 24 | 0 | 8 |  |
| `_identity` | function | 23 | 2 | 24 | server/live_voice/native_interaction_carrier.py, server/live_voice/native_interaction_runtime.py |
| `_ProviderResponse` | value | 20 | 0 | 12 |  |
| `_HARMLESS_EVENT_TYPES` | constant | 19 | 0 | 2 |  |
| `_BUSINESS_INSTRUCTIONS` | constant | 17 | 0 | 2 |  |
| `NativeProviderState` | value | 15 | 0 | 49 |  |
| `_RESPONSE_RESOURCE_KEYS` | constant | 15 | 0 | 1 |  |
| `NativeEngineSnapshot` | value | 12 | 0 | 2 |  |
| `_ProviderAudioItem` | value | 12 | 0 | 4 |  |
| `_ProviderResponseRequest` | value | 12 | 0 | 12 |  |
| `NativeAudioOutput` | value | 11 | 3 | 2 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/native_interaction_carrier.py, server/live_voice/native_interaction_runtime.py |
| `_DELEGATE_SUCCESSOR_INSTRUCTIONS` | constant | 10 | 0 | 1 |  |
| `_provider_error_label` | function | 8 | 0 | 8 |  |
| `NativeEngineEvent` | value | 8 | 3 | 39 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_interaction_carrier.py |
| `_BufferedAudio` | value | 8 | 0 | 6 |  |
| `_PreparedContinuation` | value | 8 | 0 | 5 |  |
| `_BUSINESS_ARGUMENT_CORRECTION_INSTRUCTIONS` | constant | 8 | 0 | 1 |  |
| `_WORK_NOTIFICATION_INSTRUCTIONS` | constant | 8 | 0 | 1 |  |
| `NativeProviderDone` | value | 7 | 3 | 2 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/native_interaction_carrier.py, server/live_voice/native_interaction_runtime.py |
| `_cursor` | function | 6 | 0 | 9 |  |
| `NativeGeneratedTranscript` | value | 5 | 0 | 2 |  |
| `_BUSINESS_ARGUMENT_CORRECTION_EXHAUSTED` | constant | 5 | 0 | 1 |  |
| `OpenAIRealtimeNativeInteractionError` | exception | 4 | 0 | 161 |  |
| `_DelegateResult` | value | 4 | 0 | 4 |  |
| `_BusinessCallRecord` | value | 4 | 0 | 3 |  |
| `_DelegateWait` | value | 3 | 0 | 2 |  |
| `_PendingProviderControlSend` | value | 3 | 0 | 6 |  |
| `_digest_id` | function | 3 | 0 | 3 |  |
| `NATIVE_PCM_SAMPLE_RATE` | constant | 1 | 2 | 6 | gateway/live_voice/dedicated_media_registration.py, server/live_voice/native_interaction_runtime.py |
| `NATIVE_AUDIO_FRAME_BYTES` | constant | 1 | 0 | 6 |  |
| `MAX_NATIVE_INPUT_AUDIO_BYTES` | constant | 1 | 0 | 1 |  |
| `MAX_NATIVE_AUDIO_DELTA_BYTES` | constant | 1 | 1 | 1 | server/live_voice/native_interaction_runtime.py |
| `MAX_NATIVE_DELEGATE_RESULT_UTF8_BYTES` | constant | 1 | 2 | 1 | gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_interaction_runtime.py |

### `server/live_voice/native_interaction_runtime.py`（1,550 行；被 5 个生产文件导入；17 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `NativeInteractionRuntimeOwner` | owner | 1322 | 3 | 1 | server/live_voice/agent_conversation_runtime.py, server/live_voice/product_composition_registry.py, server/live_voice/product_p2_interaction_adapter.py |
| `_identity` | function | 25 | 0 | 13 |  |
| `_transcript` | function | 25 | 0 | 1 |  |
| `_RuntimeResponse` | value | 14 | 0 | 10 |  |
| `NativeInteractionRuntimeSnapshot` | value | 10 | 0 | 3 |  |
| `NativeUserHistoryAdmission` | value | 9 | 3 | 4 | server/live_voice/agent_conversation_runtime.py, server/live_voice/formal_history_writer.py, server/live_voice/product_p2_interaction_adapter.py |
| `NativeBargeAdmission` | value | 5 | 0 | 6 |  |
| `NativeHistoryAdmission` | value | 5 | 4 | 6 | server/live_voice/agent_conversation_runtime.py, server/live_voice/formal_history_writer.py, server/live_voice/product_composition_registry.py |
| `NativeDelegateResult` | value | 5 | 0 | 6 |  |
| `NativeInteractionRuntimeError` | exception | 4 | 2 | 83 | server/live_voice/native_business_router.py, server/live_voice/product_composition_registry.py |
| `NativeDelegateAdmission` | value | 4 | 0 | 5 |  |
| `NativeResponseAdmission` | value | 3 | 0 | 6 |  |
| `NativeAudioAdmission` | value | 3 | 0 | 6 |  |
| `_MAX_IDENTITY_CHARS` | constant | 1 | 0 | 1 |  |
| `_MAX_IDENTITY_UTF8_BYTES` | constant | 1 | 0 | 2 |  |
| `_MAX_NATIVE_RUNTIME_RECORDS` | constant | 1 | 0 | 1 |  |
| `_MAX_NATIVE_RESPONSE_AUDIO_ITEMS` | constant | 1 | 0 | 2 |  |

### `gateway/live_voice/native_interaction_runtime_client.py`（1,253 行；被 2 个生产文件导入；25 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `GatewayNativeInteractionRuntimeClient` | owner | 592 | 1 | 1 | gateway/channel_manager/web/app_web_handlers.py |
| `_validate_method_result` | function | 195 | 0 | 1 |  |
| `_canonical_native_user_history` | function | 79 | 0 | 1 |  |
| `_validate_business_context_result` | function | 54 | 0 | 3 |  |
| `_canonical_native_assistant_projection` | function | 40 | 0 | 1 |  |
| `_canonical_audio_presentation_unit` | function | 30 | 0 | 2 |  |
| `_request_identity` | function | 23 | 0 | 1 |  |
| `_validate_business_observation_result` | function | 19 | 0 | 2 |  |
| `_canonical_result_identity` | function | 16 | 0 | 20 |  |
| `_canonical_transcript` | function | 15 | 0 | 3 |  |
| `_canonical_delegate_result` | function | 15 | 0 | 1 |  |
| `_canonical_response_ref` | function | 14 | 0 | 5 |  |
| `_capability` | function | 11 | 0 | 1 |  |
| `_closed_result` | function | 9 | 0 | 11 |  |
| `_canonical_audio_result` | function | 9 | 0 | 1 |  |
| `GatewayNativeActivation` | value | 8 | 1 | 10 | gateway/live_voice/dedicated_media_registration.py |
| `NATIVE_INTERNAL_REQ_METHODS` | constant | 7 | 0 | 1 |  |
| `NativeRuntimeClientError` | exception | 4 | 1 | 42 | gateway/live_voice/dedicated_media_registration.py |
| `GatewayNativeRuntimeClientSnapshot` | value | 3 | 0 | 3 |  |
| `NATIVE_GATEWAY_DESCRIPTOR_KEY` | constant | 1 | 0 | 2 |  |
| `NATIVE_BROWSER_DESCRIPTOR_KEY` | constant | 1 | 1 | 2 | gateway/live_voice/dedicated_media_registration.py |
| `NATIVE_GATEWAY_CHANNEL` | constant | 1 | 0 | 3 |  |
| `_MAX_REQUEST_SECONDS` | constant | 1 | 0 | 1 |  |
| `_MAX_REQUEST_ID_CHARS` | constant | 1 | 0 | 2 |  |
| `_MAX_REQUEST_ID_BYTES` | constant | 1 | 0 | 3 |  |

### `server/live_voice/openai_realtime_session.py`（1,152 行；被 5 个生产文件导入；42 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `OpenAIRealtimeSession` | owner | 422 | 1 | 1 | server/live_voice/openai_realtime_native_engine.py |
| `RealtimeSocketCleanupOwner` | owner | 175 | 1 | 1 | server/live_voice/openai_streaming_speech.py |
| `OpenAIRealtimeSessionConfig` | value | 35 | 2 | 5 | gateway/channel_manager/web/app_web_handlers.py, server/live_voice/openai_realtime_native_engine.py |
| `_client_payload` | function | 35 | 0 | 2 |  |
| `_decode_provider_event` | function | 30 | 0 | 1 |  |
| `_negotiated_session_id` | function | 30 | 0 | 2 |  |
| `_connect_socket` | function | 28 | 0 | 1 |  |
| `_UniqueSocketFinalizer` | class | 27 | 0 | 1 |  |
| `default_realtime_socket_factory` | function | 22 | 2 | 2 | server/live_voice/openai_streaming_speech.py, server/live_voice/speech_socket_diagnostics.py |
| `_encode_client_event` | function | 21 | 0 | 1 |  |
| `official_realtime_url` | function | 20 | 1 | 2 | server/live_voice/openai_streaming_speech.py |
| `_safe_label` | function | 19 | 1 | 6 | server/live_voice/openai_streaming_speech.py |
| `_transport_failure_fields` | function | 18 | 0 | 2 |  |
| `validate_official_openai_api_base` | function | 16 | 1 | 3 | server/live_voice/openai_streaming_speech.py |
| `RealtimeTransport` | value | 10 | 1 | 1 | server/live_voice/openai_streaming_speech.py |
| `_await_socket_close` | function | 10 | 0 | 2 |  |
| `OpenAIRealtimeEvent` | value | 9 | 2 | 9 | server/live_voice/native_continuation_preparation.py, server/live_voice/openai_realtime_native_engine.py |
| `_required_secret` | function | 9 | 1 | 1 | server/live_voice/openai_streaming_speech.py |
| `_bounded_timeout` | function | 9 | 0 | 5 |  |
| `RealtimeSocketCleanupSnapshot` | value | 8 | 0 | 4 |  |
| `RealtimeSessionSnapshot` | value | 8 | 0 | 4 |  |
| `RealtimeSessionState` | value | 7 | 0 | 24 |  |
| `_unique_json_object` | function | 7 | 0 | 1 |  |
| `RealtimeSocket` | value | 6 | 1 | 15 | server/live_voice/openai_streaming_speech.py |
| `_close_socket` | function | 6 | 1 | 1 | server/live_voice/openai_streaming_speech.py |
| `_TIMED_PROVIDER_EVENTS` | constant | 5 | 0 | 1 |  |
| `_TRANSPORT_EXCEPTION_NAMES` | constant | 5 | 0 | 1 |  |
| `_TIMED_CLIENT_EVENTS` | constant | 4 | 0 | 2 |  |
| `OpenAIRealtimeSessionError` | exception | 4 | 1 | 27 | server/live_voice/openai_realtime_native_engine.py |
| `_SocketCloseResult` | value | 4 | 0 | 5 |  |
| `RealtimeSocketFactory` | constant | 3 | 2 | 3 | server/live_voice/openai_realtime_native_engine.py, server/live_voice/openai_streaming_speech.py |
| `_CleanupOutcome` | value | 3 | 1 | 11 | server/live_voice/openai_streaming_speech.py |
| `_SocketCleanupEntry` | value | 3 | 0 | 4 |  |
| `_is_process_control` | function | 2 | 1 | 1 | server/live_voice/openai_streaming_speech.py |
| `MAX_REALTIME_WIRE_MESSAGE_BYTES` | constant | 1 | 1 | 5 | server/live_voice/openai_streaming_speech.py |
| `REALTIME_SOCKET_CLOSE_TIMEOUT_SECONDS` | constant | 1 | 1 | 3 | server/live_voice/openai_streaming_speech.py |
| `_MAX_SAFE_LABEL_CHARS` | constant | 1 | 0 | 1 |  |
| `_MAX_SAFE_LABEL_UTF8_BYTES` | constant | 1 | 0 | 1 |  |
| `_MAX_API_KEY_CHARS` | constant | 1 | 0 | 1 |  |
| `_MAX_PROVIDER_EVENTS` | constant | 1 | 0 | 1 |  |

### `server/live_voice/native_work_runtime.py`（959 行；被 3 个生产文件导入；13 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `NativeWorkRuntime` | owner | 695 | 2 | 0 | server/live_voice/native_business_router.py, server/live_voice/native_work_journal.py |
| `NativeWorkSnapshot` | value | 99 | 1 | 14 | server/live_voice/native_work_journal.py |
| `NativeWorkControl` | value | 38 | 1 | 4 | server/live_voice/agent_conversation_runtime.py |
| `_text` | function | 15 | 0 | 7 |  |
| `context_identity` | function | 12 | 2 | 0 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_business_router.py |
| `NativeWorkState` | value | 9 | 1 | 53 | server/live_voice/native_work_journal.py |
| `_TERMINAL` | constant | 9 | 0 | 3 |  |
| `NativeWorkViolation` | exception | 7 | 1 | 31 | server/live_voice/native_work_journal.py |
| `NativeWorkCancelled` | class | 7 | 1 | 1 | server/live_voice/agent_conversation_runtime.py |
| `_Record` | value | 5 | 0 | 11 |  |
| `_now` | function | 2 | 1 | 3 | server/live_voice/native_business_router.py |
| `T` | constant | 1 | 0 | 3 |  |
| `NativeWorkRunner` | constant | 1 | 0 | 3 |  |

### `server/live_voice/native_interaction_contract.py`（852 行；被 11 个生产文件导入；31 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `NativeAudioObservation` | value | 105 | 2 | 2 | server/live_voice/native_interaction_carrier.py, server/live_voice/native_interaction_runtime.py |
| `NativeDelegateProposal` | value | 102 | 4 | 11 | server/live_voice/native_business_contract.py, server/live_voice/native_interaction_carrier.py, server/live_voice/native_interaction_runtime.py |
| `NativeTurnCommit` | value | 97 | 4 | 10 | server/live_voice/conversation_runtime_loop.py, server/live_voice/native_interaction_carrier.py, server/live_voice/native_interaction_runtime.py |
| `NativeContractLedger` | owner | 77 | 1 | 1 | server/live_voice/openai_realtime_native_engine.py |
| `NativePresentationCursor` | value | 72 | 5 | 2 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_interaction_runtime.py |
| `NativeInputTranscript` | value | 68 | 3 | 2 | server/live_voice/native_interaction_carrier.py, server/live_voice/native_interaction_runtime.py, server/live_voice/openai_realtime_native_engine.py |
| `NativeInteractionBinding` | value | 51 | 9 | 15 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/agent_conversation_runtime.py |
| `_scope` | function | 21 | 2 | 2 | server/live_voice/agent_conversation_runtime.py, server/live_voice/conversation_runtime_loop.py |
| `_optional_transcript` | function | 18 | 0 | 2 |  |
| `_COMMIT_KEYS` | constant | 17 | 0 | 1 |  |
| `_delegate_text` | function | 16 | 0 | 2 |  |
| `_identity` | function | 15 | 3 | 27 | server/live_voice/native_interaction_carrier.py, server/live_voice/native_interaction_runtime.py, server/live_voice/openai_realtime_native_engine.py |
| `_closed_mapping` | function | 12 | 0 | 9 |  |
| `_AUDIO_OBSERVATION_KEYS` | constant | 12 | 0 | 1 |  |
| `_INPUT_TRANSCRIPT_KEYS` | constant | 12 | 0 | 1 |  |
| `_DELEGATE_KEYS` | constant | 12 | 0 | 1 |  |
| `NativeInteractionContractViolation` | exception | 10 | 1 | 35 | server/live_voice/openai_realtime_native_engine.py |
| `_utf8_length` | function | 7 | 0 | 3 |  |
| `_cursor` | function | 7 | 1 | 10 | server/live_voice/openai_realtime_native_engine.py |
| `_positive_generation` | function | 7 | 0 | 7 |  |
| `_unique_json_object` | function | 7 | 0 | 1 |  |
| `_contains_control` | function | 5 | 0 | 3 |  |
| `NATIVE_INTERACTION_CONTRACT_VERSION` | constant | 1 | 5 | 9 | gateway/live_voice/dedicated_media_registration.py, gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_interaction_carrier.py |
| `MAX_NATIVE_AUDIO_SAMPLE_COUNT` | constant | 1 | 0 | 2 |  |
| `MAX_NATIVE_AUDIO_PROPOSAL_BATCH` | constant | 1 | 3 | 1 | gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_interaction_runtime.py, server/live_voice/product_composition_registry.py |
| `MAX_NATIVE_DELEGATE_UTF8_BYTES` | constant | 1 | 0 | 2 |  |
| `MAX_NATIVE_TRANSCRIPT_UTF8_BYTES` | constant | 1 | 3 | 1 | gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_interaction_carrier.py, server/live_voice/native_interaction_runtime.py |
| `_MAX_IDENTITY_CHARS` | constant | 1 | 3 | 1 | server/live_voice/native_interaction_carrier.py, server/live_voice/native_interaction_runtime.py, server/live_voice/openai_realtime_native_engine.py |
| `_MAX_IDENTITY_UTF8_BYTES` | constant | 1 | 2 | 1 | server/live_voice/native_interaction_runtime.py, server/live_voice/openai_realtime_native_engine.py |
| `_MAX_CONTRACT_LEDGER_CAPACITY` | constant | 1 | 0 | 1 |  |
| `_RESPONSE_REF_KEYS` | constant | 1 | 0 | 1 |  |

### `server/live_voice/native_work_journal.py`（823 行；被 1 个生产文件导入；11 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `SqliteNativeWorkJournal` | owner | 651 | 1 | 1 | server/live_voice/native_business_router.py |
| `_COLUMNS` | constant | 37 | 0 | 1 |  |
| `_TRANSITIONS` | constant | 34 | 0 | 1 |  |
| `_origin_identity` | function | 23 | 0 | 2 |  |
| `_IMMUTABLE_FIELDS` | constant | 14 | 0 | 1 |  |
| `_event_identity` | function | 13 | 0 | 4 |  |
| `_scope_digest` | function | 7 | 0 | 9 |  |
| `_digest` | function | 2 | 0 | 10 |  |
| `_SCHEMA_VERSION` | constant | 1 | 0 | 11 |  |
| `_MAX_PAYLOAD_BYTES` | constant | 1 | 0 | 3 |  |
| `_SUPPRESSION_REASONS` | constant | 1 | 0 | 2 |  |

### `server/live_voice/native_business_router.py`（543 行；被 1 个生产文件导入；2 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `NativeBusinessRouter` | owner | 508 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_now` | function | 2 | 0 | 2 |  |

### `server/live_voice/native_interaction_carrier.py`（516 行；被 2 个生产文件导入；17 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `NativeInteractionProposal` | value | 218 | 2 | 3 | gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/product_composition_registry.py |
| `_action_from_dict` | function | 59 | 0 | 2 |  |
| `_done_from_dict` | function | 51 | 0 | 1 |  |
| `_identity` | function | 25 | 0 | 10 |  |
| `_response_from_dict` | function | 18 | 0 | 1 |  |
| `_PROPOSAL_KEYS` | constant | 12 | 0 | 1 |  |
| `_closed` | function | 12 | 0 | 5 |  |
| `_DONE_KEYS` | constant | 10 | 0 | 1 |  |
| `NativeCarrierViolation` | exception | 10 | 1 | 25 | server/live_voice/product_composition_registry.py |
| `_done_to_dict` | function | 9 | 0 | 1 |  |
| `_action_to_dict` | function | 8 | 0 | 2 |  |
| `_response_to_dict` | function | 6 | 0 | 1 |  |
| `_ACTION_KEYS` | constant | 3 | 0 | 1 |  |
| `_ACTION_PAYLOAD_KEYS` | constant | 1 | 0 | 1 |  |
| `_RESPONSE_KEYS` | constant | 1 | 0 | 1 |  |
| `_MAX_IDENTITY_CHARS` | constant | 1 | 0 | 1 |  |
| `_MAX_IDENTITY_BYTES` | constant | 1 | 0 | 2 |  |

### `server/live_voice/native_continuation_preparation.py`（403 行；被 1 个生产文件导入；6 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `PreparedProviderOutput` | value | 355 | 1 | 0 | server/live_voice/openai_realtime_native_engine.py |
| `_transcript` | function | 9 | 0 | 3 |  |
| `_identity` | function | 6 | 1 | 11 | server/live_voice/openai_realtime_native_engine.py |
| `PreparedOutputViolation` | exception | 4 | 1 | 51 | server/live_voice/openai_realtime_native_engine.py |
| `MAX_PREPARED_OUTPUT_BYTES` | constant | 1 | 0 | 1 |  |
| `MAX_PREPARED_OUTPUT_EVENTS` | constant | 1 | 0 | 1 |  |

### `gateway/live_voice/native_response_downlink.py`（311 行；被 1 个生产文件导入；4 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `NativeResponseDownlinkSource` | class | 224 | 1 | 2 | gateway/live_voice/dedicated_media_registration.py |
| `NativeDownlinkPresentationUnit` | value | 48 | 1 | 5 | gateway/live_voice/dedicated_media_registration.py |
| `_SHA256` | constant | 1 | 0 | 1 |  |
| `_MAX_SAFE_INTEGER` | constant | 1 | 0 | 1 |  |

### `server/live_voice/native_business_contract.py`（251 行；被 8 个生产文件导入；12 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `NativeBusinessAction` | value | 73 | 2 | 5 | server/live_voice/native_business_context.py, server/live_voice/native_business_tools.py |
| `native_business_tool` | function | 58 | 0 | 0 |  |
| `NativeBusinessProposal` | value | 51 | 7 | 0 | gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_business_router.py, server/live_voice/native_business_tools.py |
| `_text` | function | 10 | 0 | 2 |  |
| `NativeBusinessViolation` | exception | 9 | 4 | 20 | server/live_voice/native_business_context.py, server/live_voice/native_business_router.py, server/live_voice/native_business_tools.py |
| `_TEXT_ARGUMENTS` | constant | 7 | 0 | 3 |  |
| `NATIVE_BUSINESS_OPERATIONS` | constant | 5 | 0 | 4 |  |
| `_FIELDS` | constant | 2 | 0 | 4 |  |
| `NATIVE_BUSINESS_CONTRACT_VERSION` | constant | 1 | 3 | 2 | gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_business_router.py, server/live_voice/product_composition_registry.py |
| `NATIVE_BUSINESS_TOOL_NAME` | constant | 1 | 1 | 1 | server/live_voice/native_business_tools.py |
| `_COLLECTION` | constant | 1 | 0 | 2 |  |
| `_REVISION_REQUIRED` | constant | 1 | 0 | 2 |  |

### `server/live_voice/native_interaction_config.py`（168 行；被 3 个生产文件导入；17 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `select_interaction_engine_environment` | function | 41 | 2 | 1 | gateway/channel_manager/web/app_web_handlers.py, server/live_voice/product_composition_registry.py |
| `_model` | function | 28 | 0 | 1 |  |
| `_output_tokens_environment` | function | 13 | 0 | 1 |  |
| `validate_native_max_output_tokens` | function | 10 | 1 | 2 | server/live_voice/openai_realtime_native_engine.py |
| `validate_native_vad_eagerness` | function | 8 | 1 | 2 | server/live_voice/openai_realtime_native_engine.py |
| `NativeInteractionSelection` | value | 5 | 0 | 4 |  |
| `NativeInteractionConfigurationError` | exception | 4 | 1 | 10 | gateway/channel_manager/web/app_web_handlers.py |
| `InteractionEngineKind` | value | 3 | 2 | 5 | gateway/channel_manager/web/app_web_handlers.py, server/live_voice/product_composition_registry.py |
| `INTERACTION_ENGINE_ENV` | constant | 1 | 0 | 2 |  |
| `NATIVE_REALTIME_MODEL_ENV` | constant | 1 | 0 | 2 |  |
| `NATIVE_VAD_EAGERNESS_ENV` | constant | 1 | 0 | 2 |  |
| `NATIVE_MAX_OUTPUT_TOKENS_ENV` | constant | 1 | 0 | 2 |  |
| `DEFAULT_NATIVE_REALTIME_MODEL` | constant | 1 | 0 | 2 |  |
| `DEFAULT_NATIVE_VAD_EAGERNESS` | constant | 1 | 1 | 2 | server/live_voice/openai_realtime_native_engine.py |
| `DEFAULT_NATIVE_MAX_OUTPUT_TOKENS` | constant | 1 | 1 | 3 | server/live_voice/openai_realtime_native_engine.py |
| `_MAX_MODEL_CHARS` | constant | 1 | 0 | 2 |  |
| `_MAX_MODEL_UTF8_BYTES` | constant | 1 | 0 | 1 |  |

### `server/live_voice/native_business_tools.py`（165 行；被 2 个生产文件导入；11 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `native_business_proposal_from_function_call` | function | 47 | 1 | 0 | server/live_voice/openai_realtime_native_engine.py |
| `_property` | function | 32 | 0 | 1 |  |
| `_OPERATIONS` | constant | 15 | 0 | 5 |  |
| `_DESCRIPTIONS` | constant | 15 | 0 | 1 |  |
| `native_business_tools` | function | 13 | 2 | 0 | server/live_voice/native_continuation_preparation.py, server/live_voice/openai_realtime_native_engine.py |
| `_unique_object` | function | 7 | 0 | 1 |  |
| `_invalid_constant` | function | 2 | 0 | 1 |  |
| `_FUNCTION_OPERATIONS` | constant | 1 | 0 | 3 |  |
| `NATIVE_BUSINESS_FUNCTION_NAMES` | constant | 1 | 2 | 1 | server/live_voice/native_continuation_preparation.py, server/live_voice/openai_realtime_native_engine.py |
| `_ACTION_FIELDS` | constant | 1 | 0 | 1 |  |
| `_MAX_ARGUMENT_UTF8_BYTES` | constant | 1 | 0 | 1 |  |

### `server/live_voice/native_agent_model.py`（128 行；被 1 个生产文件导入；9 个顶层 symbol，其中 1 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `resolve_native_agent_model` | function | 25 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `NativeAgentModelSelection` | value | 17 | 0 | 7 |  |
| `NativeAgentModelConfirmation` | value | 15 | 0 | 4 |  |
| `parse_native_agent_model_confirmation` | function | 13 | 0 | 0 |  |
| `_text` | function | 10 | 0 | 3 |  |
| `_invalid` | function | 6 | 0 | 5 |  |
| `parse_native_agent_model_selection` | function | 5 | 1 | 0 | server/live_voice/product_composition_registry.py |
| `_closed` | function | 4 | 0 | 2 |  |
| `AGENT_MODEL_SELECTION_VERSION` | constant | 1 | 0 | 2 |  |

### `server/live_voice/native_business_context.py`（115 行；被 1 个生产文件导入；5 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `NativeBusinessContextStore` | owner | 37 | 1 | 0 | server/live_voice/native_business_router.py |
| `select_conversation_history` | function | 25 | 1 | 0 | server/live_voice/native_business_router.py |
| `formal_context` | function | 12 | 1 | 1 | server/live_voice/native_business_router.py |
| `NativeContextSelection` | value | 8 | 0 | 2 |  |
| `_digest` | function | 2 | 0 | 2 |  |

### `server/live_voice/native_foreground.py`（85 行；被 3 个生产文件导入；4 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `NativeForegroundControl` | value | 56 | 1 | 1 | server/live_voice/product_composition_registry.py |
| `NativeForegroundInterrupted` | exception | 3 | 1 | 1 | server/live_voice/agent_conversation_runtime.py |
| `NATIVE_FOREGROUND` | constant | 3 | 3 | 2 | server/live_voice/agent_conversation_runtime.py, server/live_voice/native_work_runtime.py, server/live_voice/product_composition_registry.py |
| `T` | constant | 1 | 1 | 5 | server/live_voice/native_work_runtime.py |

### `server/live_voice/native_business_observation.py`（65 行；被 5 个生产文件导入；6 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `project_native_receipt` | function | 35 | 1 | 0 | server/live_voice/openai_realtime_native_engine.py |
| `observation_cursor` | function | 10 | 3 | 0 | gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_business_router.py, server/live_voice/native_work_runtime.py |
| `canonical_native_receipt` | function | 4 | 1 | 0 | server/live_voice/native_business_router.py |
| `NATIVE_BUSINESS_OBSERVATION_VERSION` | constant | 1 | 3 | 0 | gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_business_router.py, server/live_voice/product_composition_registry.py |
| `NATIVE_PROVIDER_RECEIPT_VERSION` | constant | 1 | 0 | 1 |  |
| `MAX_OBSERVATION_WAIT_MS` | constant | 1 | 3 | 0 | gateway/live_voice/native_interaction_runtime_client.py, server/live_voice/native_business_router.py, server/live_voice/native_work_runtime.py |

### `server/live_voice/native_business_encoding.py`（53 行；被 1 个生产文件导入；5 个顶层 symbol，其中 0 个公开 symbol 在其他生产文件与本文件内都无引用）

| symbol | 类型 | 行 | callers | 文件内引用 | 调用方示例 |
|---|---|---:|---:|---:|---|
| `compact_native_business_output` | function | 22 | 1 | 0 | server/live_voice/openai_realtime_native_engine.py |
| `_compact_string` | function | 5 | 0 | 1 |  |
| `_reject_nonstandard_number` | function | 2 | 0 | 1 |  |
| `_MAX_OUTPUT_UTF8_BYTES` | constant | 1 | 0 | 1 |  |
| `_JSON_STRING` | constant | 1 | 0 | 1 |  |
