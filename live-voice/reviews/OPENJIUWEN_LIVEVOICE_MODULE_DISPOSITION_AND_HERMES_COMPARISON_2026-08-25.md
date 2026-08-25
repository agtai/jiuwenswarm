# OpenJiuwen LiveVoice module disposition and Hermes comparison — 2026-08-25

Status: Task 1 machine inventory complete; 70 of 152 production paths now have
completed semantic disposition, Hermes relation and AgentCore classification.
The remaining classifications are in progress under the accepted
[scope](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md) and
[execution plan](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_EXECUTION_PLAN_2026-08-25.md).
This is a preparation review, not product progress or migration approval.

Risk: Tier 0 documentation. Any later code change keeps the risk assigned by
root `TESTING.md`.

## 1. Observed sources and moving-baseline rule

| Source | Observed branch / source | Observed HEAD | Use |
|---|---|---|---|
| Moving LiveVoice product fact | `hx/0812_live_voice_w3` | `acd873d0e93b2e82424e0d90a650df2c3515c34c` | read-only inventory and semantic truth |
| Isolated preparation evidence | `codex/livevoice-agentcore-hermes-prep` | `a663cec2b09a3daa18cbbe449fe5d9e71cf5f27e` before this review batch | tracked analysis and candidate evidence |
| Local AgentCore candidate | `codex/oj-g2-local-base` | `db8216839562de36fa24fd6f5ce807acea5a132a` | public-boundary and PR-candidate audit |
| Hermes architecture mirror | `main` | `fc9cbc872d8050c22f1192b16bc5ff4aed471e10` | read-only responsibility comparison |

The LiveVoice feature branch is still moving. These hashes make this audit
reproducible but do not become durable symbol locators. Before each semantic
batch, Main re-reads the current feature-branch HEAD and reconciles changed,
added or removed files by path and responsibility. Long-lived conclusions use
module paths, symbols, contracts and capability IDs, never source line numbers.

All four worktrees were clean when their observed source was recorded. The
preparation worktree becomes intentionally dirty only for the review documents
owned by this batch.

During Task 1 the product source advanced from `510f616d` to `1742c1b4`. The
ten intervening commits changed P3 Task presentation/bridge code, their tests
and STATUS, but none of the 31 audio/speech/media/TTS modules closed in §7.
The complete tracked-file projection and current capability matrix were rerun
on `1742c1b4` before this batch was closed.

The branch later advanced once more to `acd873d0` through a STATUS/evidence-only
P3-9 record. That commit changed no production or test path in this manifest;
the 152-path projection and completed semantic batches therefore remain valid.

## 2. Production-code manifest boundary

The manifest contains both dedicated LiveVoice modules and shared host files
with substantive LiveVoice-owned registration, lifecycle, protocol, safety or
presentation segments. A disposition for a shared host row applies only to its
LiveVoice segment; it never authorizes deleting or moving the unrelated module.

| Group | Inclusion rule | Files |
|---|---|---:|
| Backend server | immediate Python modules under `jiuwenswarm/server/live_voice` | 66 |
| Gateway | immediate Python modules under `jiuwenswarm/gateway/live_voice` | 8 |
| Shared schema | the two dedicated LiveVoice common schema modules | 2 |
| Web deployment | deployment observer and preflight modules | 2 |
| Formal Agent adapter | `server/runtime/agent_adapter/formal_live_voice.py` | 1 |
| Frontend feature | tracked files under `frontend/src/features/live-voice` | 42 |
| Frontend dedicated carrier | LiveVoice panels, styles, browser-ownership hook and Task presentation helper | 7 |
| Shared host segment | non-dedicated files with substantive LiveVoice integration code | 24 |
| **Total** | exact union, zero overlap | **152** |

The shared-host set was obtained by scanning production source outside the
dedicated paths for case-insensitive `live voice`, `live_voice`,
`live-voice`, `liveVoice` and `formal_live_voice` references, then
inspecting each hit. Pure translations, environment declarations, package
scripts and benchmark runners are support assets in §3. General JiuwenSwarm
dependencies with no LiveVoice-owned segment are dependencies, not mislabeled
LiveVoice modules.

Package `__init__` files and production CSS remain visible because they are
tracked package or carrier surfaces. Tests, fixtures, launchers, validation
scripts and environment profiles are recorded separately: they may be required
oracles or deployment owners, but are not silently counted as production code.

## 3. Test, fixture and support groups

| Group | Files | Treatment |
|---|---:|---|
| `tests/unit_tests/live_voice` | 71 | direct backend unit oracle group |
| `tests/integration/live_voice` | 4 | opt-in integration oracle group |
| Other named backend LiveVoice tests | 10 | Agent server, channel, common, gateway and Web privacy oracles |
| `tests/support/live_voice` | 2 | reusable test support |
| `tests/fixtures/live_voice*` | 13 | protocol, media, intent, composition and retirement fixtures |
| Frontend LiveVoice tests/manual harness | 35 | Web unit/integration and physical-harness support |
| `scripts/live_voice` | 28 | launcher, evidence, benchmark, historical-stage and validation assets |
| Frontend LiveVoice config/build/translation assets | 7 | two env profiles, env declarations, package scripts, benchmark script and two locale files |

These counts are grouping evidence, not test coverage or retention credit. Each
oracle follows its owning production responsibility; stage-named or experimental
assets require explicit re-home/remove decisions before deletion.

## 4. Disposition row contract

Every production path below must end with exactly one completed disposition row
containing:

| Field | Required meaning |
|---|---|
| Module | stable tracked path plus relevant public symbols; no line numbers |
| Capability domain | one stable STATUS/design capability owner |
| Responsibility | what outcome or invariant the module or LiveVoice segment owns |
| Why necessary | product, platform, safety, compatibility or support reason |
| State or authority | canonical truth, verified replica, presentation fact, Port/Adapter, stateless policy or no state |
| AgentCore relation | direct reuse, Adapter reuse, AgentCore PR candidate or LiveVoice-owned |
| Hermes relation | analogue, partial analogue, different owner or no analogue |
| Size driver | independent responsibility clusters, validation/fencing, compatibility, duplication or generated/repetitive contract |
| Proposed disposition | retain, consolidate, split, refactor, replace, re-home or remove-after-gate |
| Dependencies/evidence | contracts, tests and predecessor/successor owners |
| Confidence/open question | high/medium/low and the exact unresolved semantic question |

A filename-based guess never closes a row. Tasks 2–5 populate these fields from
source, tests, public APIs and architecture evidence.

## 5. Exact production-code path manifest

| Group | Module path |
|---|---|
| Shared host segment | `jiuwenswarm/agents/harness/common/auto_harness/project_execution.py` |
| Shared host segment | `jiuwenswarm/agents/harness/common/auto_harness/scheduler.py` |
| Shared host segment | `jiuwenswarm/agents/harness/common/auto_harness/service.py` |
| Shared host segment | `jiuwenswarm/agents/harness/common/auto_harness/task_store.py` |
| Shared host segment | `jiuwenswarm/channels/web/app_web.py` |
| Shared host segment | `jiuwenswarm/channels/web/frontend/src/App.tsx` |
| Frontend dedicated carrier | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/L0OrdinaryChromeBatchPanel.tsx` |
| Frontend dedicated carrier | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.css` |
| Frontend dedicated carrier | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx` |
| Frontend dedicated carrier | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.css` |
| Frontend dedicated carrier | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx` |
| Shared host segment | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/MessageItem.tsx` |
| Shared host segment | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx` |
| Frontend dedicated carrier | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/productTaskProgressPresentation.ts` |
| Frontend dedicated carrier | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts` |
| Shared host segment | `jiuwenswarm/channels/web/frontend/src/featureFlags.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserGatewayMediaTransport.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechRecognitionAdapter.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechSynthesisAdapter.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioPort.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserAudioDeviceSelection.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserLiveVoiceOwnership.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/conversationRuntimeReplica.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/fakeP1Vertical.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalP3TaskExperience.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskControlLeaf.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskIntentRoute.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskResultRoute.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/l0Measurement.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/l0OrdinaryChromeBatch.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceContractV2.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceRouteTelemetry.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productCompositionContract.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP2ActivationJournal.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3ProgressGenerationJournal.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3TaskTargetJournal.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productTextProgress.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/unifiedCommittedInputOwner.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/webLifecycleObservationRecorder.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/webPlatformDiagnostics.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceCore.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceMessageGate.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceStreamingSpeech.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskAdapter.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskBridge.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskClient.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskMonitor.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTurnLifecycle.ts` |
| Frontend feature | `jiuwenswarm/channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts` |
| Shared host segment | `jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts` |
| Shared host segment | `jiuwenswarm/channels/web/frontend/src/services/supplementOutputQuarantine.ts` |
| Shared host segment | `jiuwenswarm/channels/web/frontend/src/utils/tts.ts` |
| Shared host segment | `jiuwenswarm/channels/web/frontend/src/utils/ttsOutputOwnership.ts` |
| Shared host segment | `jiuwenswarm/channels/web/frontend/src/utils/ttsText.ts` |
| Web deployment | `jiuwenswarm/channels/web/live_voice_deployment_observer.py` |
| Web deployment | `jiuwenswarm/channels/web/live_voice_deployment_preflight.py` |
| Shared schema | `jiuwenswarm/common/schema/live_voice_contract.py` |
| Shared schema | `jiuwenswarm/common/schema/live_voice_contract_v2.py` |
| Shared host segment | `jiuwenswarm/common/schema/message.py` |
| Shared host segment | `jiuwenswarm/gateway/app_gateway.py` |
| Shared host segment | `jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py` |
| Shared host segment | `jiuwenswarm/gateway/channel_manager/web/web_connect.py` |
| Gateway | `jiuwenswarm/gateway/live_voice/__init__.py` |
| Gateway | `jiuwenswarm/gateway/live_voice/browser_gateway_media_transport.py` |
| Gateway | `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py` |
| Gateway | `jiuwenswarm/gateway/live_voice/dedicated_media_route.py` |
| Gateway | `jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py` |
| Gateway | `jiuwenswarm/gateway/live_voice/speech_rpc.py` |
| Gateway | `jiuwenswarm/gateway/live_voice/streaming_speech_route.py` |
| Gateway | `jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py` |
| Shared host segment | `jiuwenswarm/server/agent_ws_server.py` |
| Backend server | `jiuwenswarm/server/live_voice/__init__.py` |
| Backend server | `jiuwenswarm/server/live_voice/agent_bridge.py` |
| Backend server | `jiuwenswarm/server/live_voice/agent_bridge_runtime.py` |
| Backend server | `jiuwenswarm/server/live_voice/agent_conversation_runtime.py` |
| Backend server | `jiuwenswarm/server/live_voice/alpha_benchmark.py` |
| Backend server | `jiuwenswarm/server/live_voice/alpha_privacy_conformance.py` |
| Backend server | `jiuwenswarm/server/live_voice/batch_speech.py` |
| Backend server | `jiuwenswarm/server/live_voice/conversation_runtime.py` |
| Backend server | `jiuwenswarm/server/live_voice/conversation_runtime_loop.py` |
| Backend server | `jiuwenswarm/server/live_voice/critical_token_safety.py` |
| Backend server | `jiuwenswarm/server/live_voice/demo_fixture_contract.py` |
| Backend server | `jiuwenswarm/server/live_voice/durability_authority.py` |
| Backend server | `jiuwenswarm/server/live_voice/durability_checkpoint.py` |
| Backend server | `jiuwenswarm/server/live_voice/durability_effects.py` |
| Backend server | `jiuwenswarm/server/live_voice/durability_identity.py` |
| Backend server | `jiuwenswarm/server/live_voice/durability_readers.py` |
| Backend server | `jiuwenswarm/server/live_voice/durability_recovery_facts.py` |
| Backend server | `jiuwenswarm/server/live_voice/executor_capabilities.py` |
| Backend server | `jiuwenswarm/server/live_voice/executor_port.py` |
| Backend server | `jiuwenswarm/server/live_voice/fake_verticals.py` |
| Backend server | `jiuwenswarm/server/live_voice/formal_history_writer.py` |
| Backend server | `jiuwenswarm/server/live_voice/formal_task_models.py` |
| Backend server | `jiuwenswarm/server/live_voice/interaction_engine.py` |
| Backend server | `jiuwenswarm/server/live_voice/jiuwenswarm_agent_adapter.py` |
| Backend server | `jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py` |
| Backend server | `jiuwenswarm/server/live_voice/latency_measurement.py` |
| Backend server | `jiuwenswarm/server/live_voice/live_voice_configuration_declaration.py` |
| Backend server | `jiuwenswarm/server/live_voice/observability.py` |
| Backend server | `jiuwenswarm/server/live_voice/observability_correlation_contract.py` |
| Backend server | `jiuwenswarm/server/live_voice/observability_exporter.py` |
| Backend server | `jiuwenswarm/server/live_voice/observability_fault_harness.py` |
| Backend server | `jiuwenswarm/server/live_voice/observability_otel_codec.py` |
| Backend server | `jiuwenswarm/server/live_voice/openai_streaming_speech.py` |
| Backend server | `jiuwenswarm/server/live_voice/p2_response_generation_store.py` |
| Backend server | `jiuwenswarm/server/live_voice/p3_authenticated_composition.py` |
| Backend server | `jiuwenswarm/server/live_voice/p3_confirmation.py` |
| Backend server | `jiuwenswarm/server/live_voice/p3_model_resolution.py` |
| Backend server | `jiuwenswarm/server/live_voice/p3_product_confirmation.py` |
| Backend server | `jiuwenswarm/server/live_voice/p3_production_intent_composition.py` |
| Backend server | `jiuwenswarm/server/live_voice/persistent_task_core.py` |
| Backend server | `jiuwenswarm/server/live_voice/presentation_ledger.py` |
| Backend server | `jiuwenswarm/server/live_voice/product_authority.py` |
| Backend server | `jiuwenswarm/server/live_voice/product_composition_contract.py` |
| Backend server | `jiuwenswarm/server/live_voice/product_composition_registry.py` |
| Backend server | `jiuwenswarm/server/live_voice/product_composition_root.py` |
| Backend server | `jiuwenswarm/server/live_voice/product_observability_adapter.py` |
| Backend server | `jiuwenswarm/server/live_voice/product_observability_runtime.py` |
| Backend server | `jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py` |
| Backend server | `jiuwenswarm/server/live_voice/product_p2_readiness.py` |
| Backend server | `jiuwenswarm/server/live_voice/product_p3_text_adapter.py` |
| Backend server | `jiuwenswarm/server/live_voice/production_task_classifier.py` |
| Backend server | `jiuwenswarm/server/live_voice/production_task_intent.py` |
| Backend server | `jiuwenswarm/server/live_voice/progress_notification_arbiter.py` |
| Backend server | `jiuwenswarm/server/live_voice/project_code_executor.py` |
| Backend server | `jiuwenswarm/server/live_voice/realtime_media.py` |
| Backend server | `jiuwenswarm/server/live_voice/sli_window_contract.py` |
| Backend server | `jiuwenswarm/server/live_voice/speech_ports.py` |
| Backend server | `jiuwenswarm/server/live_voice/streaming_speech.py` |
| Backend server | `jiuwenswarm/server/live_voice/task_core.py` |
| Backend server | `jiuwenswarm/server/live_voice/task_event_subscription.py` |
| Backend server | `jiuwenswarm/server/live_voice/task_progress_return.py` |
| Backend server | `jiuwenswarm/server/live_voice/task_store.py` |
| Backend server | `jiuwenswarm/server/live_voice/telemetry_privacy_contract.py` |
| Backend server | `jiuwenswarm/server/live_voice/unified_committed_input.py` |
| Backend server | `jiuwenswarm/server/live_voice/voice_task_bridge.py` |
| Backend server | `jiuwenswarm/server/live_voice/voice_task_policy.py` |
| Shared host segment | `jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py` |
| Formal Agent adapter | `jiuwenswarm/server/runtime/agent_adapter/formal_live_voice.py` |
| Shared host segment | `jiuwenswarm/server/runtime/agent_adapter/interface.py` |
| Shared host segment | `jiuwenswarm/server/runtime/agent_adapter/interface_deep.py` |
| Shared host segment | `jiuwenswarm/server/runtime/agent_manager.py` |
| Shared host segment | `jiuwenswarm/server/runtime/session/session_history.py` |

## 6. Inventory closure

The manifest was produced from tracked paths in the clean moving LiveVoice
worktree using the dedicated-path rules and inspected shared-host scan in §2.
The union contains 152 unique paths, with zero cross-group duplicates. A
mechanical set-equality check between this table and a fresh projection is
required whenever the moving feature-branch HEAD changes and at final review.

Semantic completion is deliberately not claimed here. Tasks 2–5 must populate
all disposition fields for every path before this document can become the final
module explanation.

## 7. Completed semantic dispositions

This section is the first completed semantic batch. `LiveVoice-owned` in the
AgentCore column is a positive boundary decision: the capability is specific to
voice media, browser I/O, product composition or LiveVoice operations and must
not be moved into AgentCore merely to reduce the LiveVoice line count.

### 7.1 Backend speech and realtime-media boundaries

| Module / representative public symbols | Capability domain; responsibility and necessity | State authority | AgentCore relation | Hermes comparison | Size driver and proposed disposition | Dependencies, evidence, confidence |
|---|---|---|---|---|---|---|
| `jiuwenswarm/server/live_voice/batch_speech.py`<br>`BatchSpeechProvider`, `FormalBatchSpeechService`, `create_environment_batch_speech_provider` | **Speech Recognition / Speech Synthesis.** Defines the batch recognition/synthesis service and provider contract needed by the browser fallback and capability probes. | Owns request-local provider selection, normalization and speech result construction; it does not own conversation state. | `LiveVoice-owned`; no AgentCore reuse or downstream candidate. | Same architectural role as Hermes STT/TTS provider registries, but keeps Jiuwen capability and failure contracts. | Provider contracts, concrete provider parsing and service orchestration are combined; **SPLIT** contracts/provider/service while preserving one public speech service. | Called by Web handlers, speech RPC and dedicated-media registration; matching unit tests are the acceptance oracle. High confidence. |
| `jiuwenswarm/server/live_voice/openai_streaming_speech.py`<br>`OpenAIStreamingSpeechProvider`, `select_environment_streaming_speech` | **Speech Recognition / Speech Synthesis.** Supplies the default-off OpenAI streaming speech adapter and explicit degradation behavior. | Owns one provider session and provider protocol state; no product or Agent state. | `LiveVoice-owned`; vendor adapter is not AgentCore infrastructure. | Hermes also isolates speech providers, but its implementation is not a contract to copy. | Vendor transport, event decoding and degradation selection are combined; **SPLIT** by provider transport and degradation policy after current feature work stabilizes. | Registered through the gateway speech composition path; provider conformance tests remain required. High confidence. |
| `jiuwenswarm/server/live_voice/realtime_media.py`<br>`RealtimeMediaPort`, `RealtimeMediaRegistrationOwner`, `create_realtime_media_activation` | **Realtime Media.** Defines a conversation-neutral realtime media port, but the current product uses the gateway dedicated-media boundary instead. | Its port would own media-session activation; no production composition currently delegates authority to it. | `LiveVoice-owned`, but duplicated/uncomposed; not an AgentCore candidate. | Corresponds loosely to Hermes audio/platform abstractions, while the active Jiuwen boundary is the gateway transport. | Public factory and port have no production caller outside the module; **REMOVE AFTER GATE** or reduce to shared types only after tests confirm the gateway port is the sole owner. | Caller scan found definitions without production composition. Preserve tests as an oracle until removal is approved. Medium-high confidence. |
| `jiuwenswarm/server/live_voice/speech_ports.py`<br>`RecognitionPort`, `SynthesisPort`, `SpeechCapability` | **Speech Recognition / Speech Synthesis.** Defines deterministic provider-neutral recognition and synthesis ports needed to keep product logic independent of vendors. | Owns contracts and request/result types only. | `LiveVoice-owned`; generic to speech, not to AgentCore Agent/Tool/Task execution. | Same architectural intent as Hermes provider interfaces. | Overlaps with streaming-speech identity and capability types; **CONSOLIDATE** shared speech contracts while retaining the port boundary. | Used by batch/streaming implementations and matching conformance tests. High confidence. |
| `jiuwenswarm/server/live_voice/streaming_speech.py`<br>`NativeStreamingSpeechProvider`, `StreamingSpeechConformance`, `StreamingProviderCapability` | **Speech Recognition / Speech Synthesis.** Defines provider-neutral streaming speech conformance, events and lifecycle. | Owns stream-local lifecycle and event ordering, not conversation/product authority. | `LiveVoice-owned`; no AgentCore migration. | Mirrors Hermes' provider-neutral streaming boundary while retaining stricter Jiuwen event and failure semantics. | Capability, identity, event and lifecycle types are concentrated here; **RETAIN**, then **CONSOLIDATE** duplicated speech primitives with `speech_ports.py`. | Implemented by provider adapters and exercised by streaming conformance tests. High confidence. |
| `jiuwenswarm/gateway/live_voice/browser_gateway_media_transport.py`<br>`create_gateway_media_activation`, `BoundedMediaSender`, `StrictMediaReceiver` | **Realtime Media.** Implements the server-side browser media wire, binding, sender and receiver required by the dedicated WebSocket route. | Owns connection-local queues, sequence validation and transport lifecycle. | `LiveVoice-owned`; this is a gateway/browser protocol boundary. | Hermes has platform/audio transport adapters, but not this Jiuwen WebSocket trust boundary. | Codec/types, queues and lifecycle are combined; **RETAIN** the transport and **SPLIT** wire codec/types from queue owners if that lowers coupling. | Used by dedicated-media route and registration; protocol parity and negative-path tests are required. High confidence. |
| `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py`<br>`DedicatedMediaProductRegistry`, `register_dedicated_media_rpc_handlers` | **Realtime Media / Configuration.** Central default-off composition and lifecycle registry for dedicated media. It is necessary because one owner must bind route, speech providers, synthesis and cleanup. | Owns gateway registration, per-connection composition and cleanup authority. | `LiveVoice-owned`; composition of voice transports is not AgentCore. | Hermes has a concentrated voice-session composition root, but Jiuwen additionally requires Web gateway registration and feature gates. | Registration, lifecycle, capability probing and observability are concentrated in a large module; **SPLIT** into registration, composition, lifecycle and diagnostics without changing authority. | Constructed by `app_web_handlers.py`; broad gateway and formal Web product tests are evidence. High confidence. |
| `jiuwenswarm/gateway/live_voice/dedicated_media_route.py`<br>`create_dedicated_media_route`, `DedicatedMediaLeafCleanupOwner` | **Realtime Media.** Implements the same-origin dedicated media route and validates the media leaf protocol. | Owns route-local session validation and dispatch; registry remains composition owner. | `LiveVoice-owned`. | Similar to Hermes' voice transport leaf, but preserves Jiuwen identity, ACK and fail-closed requirements. | Route protocol handling and lifecycle are coupled; **RETAIN**, with a possible codec/validation extraction shared only by explicit schema—not by trusting frontend types. | Called by the registration owner; negative protocol and cleanup tests are mandatory. High confidence. |
| `jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py`<br>`ProductStreamingSynthesisSource` | **Speech Synthesis / Realtime Media.** Thin product bridge from streaming synthesis output to ordered media frames. | Owns only request-local projection; upstream route owns synthesis and downstream transport owns delivery. | `LiveVoice-owned`. | Comparable to Hermes' streaming TTS consumer boundary. | Already narrow; **RETAIN AS THIN BRIDGE** and resist absorbing route or transport state. | Used by dedicated-media registration. High confidence. |
| `jiuwenswarm/gateway/live_voice/speech_rpc.py`<br>`register_speech_rpc_handlers` | **Speech Recognition / Speech Synthesis.** Registers the gateway-local batch speech RPC surface used by Web clients. | Owns RPC validation/delegation only. | `LiveVoice-owned`; not an AgentCore RPC. | No useful direct Hermes analogue beyond an API leaf. | Already narrow; **RETAIN AS ENTRY LEAF**. | Composed by Web handlers and delegates to the batch speech service. High confidence. |
| `jiuwenswarm/gateway/live_voice/streaming_speech_route.py`<br>`StreamingRecognitionRouteOwner` | **Speech Recognition.** Owns the gateway product route for streaming recognition, including fallback and event projection. | Owns recognition-route lifecycle; provider owns provider session and product route owns client delivery. | `LiveVoice-owned`. | Same pipeline position as Hermes streaming STT consumption, with Jiuwen gateway/fail-closed contracts. | Route, fallback and projection are combined; **RETAIN**, then **SPLIT** fallback and event projection if they can remain pure. | Composed by handlers/registration and covered by streaming route tests. High confidence. |
| `jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py`<br>`StreamingSynthesisRouteOwner` | **Speech Synthesis.** Owns product streaming synthesis requests, buffering and pull/delivery coordination. | Owns synthesis-route state and ordered buffering; media transport owns final frame delivery. | `LiveVoice-owned`. | Same pipeline position as Hermes streaming TTS consumer and playout feeder. | Route state, buffering and pull protocol are concentrated; **SPLIT** route state from buffering/pull mechanics while retaining one authority. | Composed by the dedicated-media registry; interruption, ordering and cleanup tests are required. High confidence. |
| `jiuwenswarm/channels/web/live_voice_deployment_observer.py`<br>`observe_live_voice_deployment_runtime`, `LiveVoiceDeploymentObservationResult` | **Observability / Configuration cleanup.** Deployment-time observer for streaming readiness and runtime evidence. | Owns observation state only; it must not become product authority. | `LiveVoice-owned support`; no AgentCore relation. | No product-architecture analogue is needed. | Operational evidence logic is large relative to the product path; **RE-HOME** under LiveVoice validation tooling after current acceptance, preserving its executable evidence role. | Invoked by LiveVoice deployment/validation flows. Medium-high confidence. |
| `jiuwenswarm/channels/web/live_voice_deployment_preflight.py`<br>`evaluate_live_voice_deployment_preflight`, `DeploymentPreflightResult` | **Configuration cleanup / Automated verification.** Performs deployment preflight checks before the streaming path is treated as usable. | Owns validation results only. | `LiveVoice-owned support`. | No Hermes analogue is required. | **RE-HOME** beside validation tooling; do not fold preflight policy into runtime modules. | Deployment scripts and operator acceptance depend on it. High confidence. |

### 7.2 Browser audio and product speech boundaries

| Module / representative public symbols | Capability domain; responsibility and necessity | State authority | AgentCore relation | Hermes comparison | Size driver and proposed disposition | Dependencies, evidence, confidence |
|---|---|---|---|---|---|---|
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts`<br>`BrowserAudioIOAdapter`, `inspectBrowserAudioPlatform` | **Audio Device & browser I/O.** Implements browser device capture, playback, acknowledgements and fencing for the formal product route. | Owns browser audio-device and playout lifecycle; it does not own conversation or task state. | `LiveVoice-owned`; browser media I/O does not belong in AgentCore. | Covers Hermes AudioRecorder, playback and platform-adapter roles, with additional browser ACK/fencing. | Multiple audio lifecycle roles are concentrated; **SPLIT** device/capture/playout-confirmation helpers while retaining one browser audio authority. | Instantiated by `productP1VoiceRoute.ts`; fake adapter and browser route tests are oracles. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts`<br>`createBrowserDedicatedMediaRoute`, `BrowserDedicatedMediaSocketLeaf` | **Realtime Media.** Binds the browser-side dedicated media connection to the product route. | Owns browser route lifecycle and validated event dispatch. | `LiveVoice-owned`. | Comparable to a Hermes transport leaf, but implements Jiuwen's WebSocket protocol and browser failure rules. | Protocol validation and lifecycle are coupled; **RETAIN**, with a possible pure validation extraction. | Used by `productP1VoiceRoute.ts`; must remain parity-tested with the gateway route. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserGatewayMediaTransport.ts`<br>`createBrowserGatewayMediaActivation`, `BoundedMediaSender`, `StrictMediaReceiver`, `BrowserGatewayMediaRegistrationOwner` | **Realtime Media.** Implements browser wire types, codec, sender, receiver and registration for gateway media. | Owns browser connection queues and transport sequence state. | `LiveVoice-owned`. | Hermes abstracts audio transports but has no equivalent Jiuwen browser/gateway trust boundary. | Wire types, codec and queue owners are combined; **SPLIT** only along those internal seams and keep explicit cross-language parity checks. | Used by browser dedicated-media route/product route. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechRecognitionAdapter.ts`<br>`BrowserSpeechRecognitionAdapter` | **Speech Recognition / legacy compatibility.** Adapts browser speech recognition for the legacy integrated route. | Owns a legacy browser-recognition session only. | `LiveVoice-owned legacy`; no AgentCore relation. | Hermes provider abstraction does not justify retaining a browser-only duplicate path. | Production callers are confined to `integratedP1Route.ts`; **REMOVE AFTER GATE** with the legacy lane, preserving any still-useful tests as oracles. | Caller scan found only the legacy integrated route. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechSynthesisAdapter.ts`<br>`BrowserSpeechSynthesisAdapter` | **Speech Synthesis / legacy compatibility.** Adapts browser speech synthesis for the legacy integrated route. | Owns legacy browser speech-synthesis lifecycle. | `LiveVoice-owned legacy`. | Hermes TTS providers do not require this duplicate browser path. | Confined to the legacy lane; **REMOVE AFTER GATE** once formal gateway synthesis owns accepted playout. | Caller scan found only `integratedP1Route.ts`. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedP1Route.ts`<br>`createIntegratedP1Route` | **Integrated Web / legacy compatibility.** Legacy browser-local P1 route predating the formal gateway product route. | Owns a parallel legacy recognition/synthesis state machine. | `LiveVoice-owned legacy`, not AgentCore. | It resembles an all-local Hermes voice loop, but keeping two LiveVoice owners creates ambiguity. | Duplicate authority is the size driver; **REPLACE/REMOVE AFTER GATE** with `useLiveVoiceDemo` when formal route acceptance and rollback evidence allow. | Production caller is the legacy demo hook. High confidence on classification; removal timing remains gated. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js`<br>registered AudioWorklet processor `jiuwenswarm-live-voice-capture-v1` | **Audio Device & browser I/O.** AudioWorklet processor that captures PCM at the browser audio edge. | Owns worklet-local buffering only. | `LiveVoice-owned`. | Same audio-edge role as Hermes recorder internals. | Already focused; **RETAIN**. | Loaded by `browserAudioIOAdapter.ts`; browser audio tests and manual device validation apply. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioPort.ts`<br>`AudioPort`, `createCapturedAudioFrame`, `createAudioRenderPlan` | **Audio Device & browser I/O.** Formal browser audio port and shared audio types that keep product routing testable. | Contract only; concrete adapter owns device state. | `LiveVoice-owned`. | Matches Hermes' platform/audio abstraction intent. | Contains production and fake-facing surface; **RETAIN CONTRACT**, then remove fake-only members after oracle migration if unused. | Used by real/fake audio adapters and product-route tests. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserAudioDeviceSelection.ts`<br>`BrowserAudioDeviceSelectionOwner` | **Audio Device & browser I/O / Integrated Web.** Discovers, selects and persists the user's browser audio-device choice. | Owns product-local device selection, not the media stream itself. | `LiveVoice-owned`. | Partial analogue to Hermes platform/device selection, adapted for browser permissions. | **RETAIN** as a separate product/device owner; do not merge permission policy into transport. | Used by `LiveVoiceIntegratedRoutePanel.tsx`. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/browserLiveVoiceOwnership.ts`<br>`createBrowserLiveVoiceOwnership`, `createBrowserLiveVoiceOwnershipBarrier` | **Audio Device & browser I/O / Integrated Web.** Enforces browser-global capture/playout ownership so parallel UI paths cannot mutate the same devices. | Owns the browser process ownership lease and cleanup. | `LiveVoice-owned`. | Hermes uses process-global interruption flags, which are not a safe substitute for Jiuwen's explicit ownership/fencing. | **RETAIN**, then evaluate consolidation with output ownership only after legacy TTS is retired. | Mounted through `useProductVoiceBrowserOwnership.ts`; negative tests must prove forbidden side effects are zero. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts`<br>`GatewayBatchSpeechClient`, `capturedFramesToPcm16Wav` | **Speech Recognition / Speech Synthesis.** Browser client for gateway batch speech, including wire validation and PCM conversion. | Owns request-local client lifecycle; gateway service owns provider execution. | `LiveVoice-owned`. | Equivalent pipeline role to a client of Hermes speech providers, but the Web RPC contract is Jiuwen-specific. | Wire validation, PCM conversion, capability and client logic are concentrated; **SPLIT** pure codec/conversion from client state. | Used by `productP1VoiceRoute.ts`; client/server contract tests apply. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`<br>`ProductP1VoiceRouteOwner` | **Conversation Runtime / Integrated Web.** Current formal browser product state machine coordinating capture, recognition, synthesis, playback and diagnostics. | Owns product-route lifecycle and transitions; it delegates device, transport and provider state to their ports. | `LiveVoice-owned`; this is the voice product composition root, not AgentCore. | Corresponds to Hermes' voice-session loop while preserving Jiuwen committed-input, identity, ACK and failure contracts. | Several state-machine facets are concentrated in one large module; **SPLIT** capture, recognition, playout and diagnostics into pure/projected subcomponents without creating parallel authorities. | Imports the formal audio adapter, gateway media/speech clients and L0 measurement. Highest-risk refactor; high classification confidence. |
| `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts`<br>`useProductVoiceBrowserOwnership` | **Integrated Web.** React lifecycle hook that mounts the formal browser ownership barrier and guarantees cleanup. | Owns hook lifetime only; `browserLiveVoiceOwnership.ts` owns the lease semantics. | `LiveVoice-owned`. | No distinct Hermes analogue is needed. | Already a thin carrier; **RETAIN AS THIN HOOK**. | Used by the integrated product panel/host composition. High confidence. |

### 7.3 Shared text and output-ownership segments

| Module or segment / representative public symbols | Capability domain; responsibility and necessity | State authority | AgentCore relation | Hermes comparison | Size driver and proposed disposition | Dependencies, evidence, confidence |
|---|---|---|---|---|---|---|
| `jiuwenswarm/channels/web/frontend/src/utils/ttsText.ts`<br>`makeLiveVoiceTextSpeakable`, `sanitizeLiveVoiceTtsText`, `splitLiveVoiceTtsText` | **Speech Synthesis.** Sanitizes and chunks multilingual/Markdown-heavy text before speech; this prevents malformed, silently truncated or unbounded TTS requests. | Pure transformation; no runtime authority. | `LiveVoice-owned speech utility`, not AgentCore. | Direct architectural analogue to Hermes `SentenceChunker`, but Jiuwen's implementation covers Chinese and technical/Markdown text and should not be replaced for parity. | The useful generic speech-text contract is hidden under a broad utility name; **RE-HOME/RENAME** to an explicit speech-text module and reuse from all TTS paths. | Imported through `tts.ts` and LiveVoice callers; pure unit tests are the oracle. High confidence. |
| `jiuwenswarm/channels/web/frontend/src/utils/ttsOutputOwnership.ts`<br>`acquireLiveVoiceTtsOutputOwnership`, `beginServerTtsOutput`, `canCompleteServerTtsOutput` | **Speech Synthesis / Integrated Web compatibility.** Fences legacy/manual server TTS against formal LiveVoice playout. | Owns browser output-ownership revision and leases for shared/legacy TTS. | `LiveVoice-owned host integration segment`. | Hermes' global interrupt flag is less explicit and is not a replacement. | Exists because two output paths coexist; **CONSOLIDATE AFTER GATE** with formal browser ownership once legacy/manual output integration is retired. | Used by shared TTS and message rendering. High confidence; retirement timing is gated. |
| LiveVoice segment of `jiuwenswarm/channels/web/frontend/src/utils/tts.ts`<br>LiveVoice text exports plus shared `stopAllTts`, `fetchTtsAudio`, `playAudioBase64` interactions | **Speech Synthesis / shared compatibility.** The module remains the shared legacy/manual server-TTS owner and also re-exports LiveVoice text helpers; only those LiveVoice integrations are classified here. | Owns the shared global legacy audio instance and stop event; it does not own the formal LiveVoice playout route. | Shared host module; LiveVoice-specific exports/interruption integration are `LiveVoice-owned`, while the whole module is not a downstream candidate. | Hermes' TTS service and interrupt path are only partial analogues because this is Jiuwen shared-chat compatibility. | **RETAIN** the shared TTS owner; **RE-HOME** LiveVoice text exports to the named speech-text boundary and later consolidate stop/ownership integration after legacy-route retirement. | Used by shared chat/message flows; caller graph and negative output-fence tests govern changes. High confidence. |
| LiveVoice segment of `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/MessageItem.tsx`<br>manual-message TTS output fence | **Integrated Web / Speech Synthesis compatibility.** Prevents manual historical-message TTS from playing while LiveVoice owns audio output. The rest of the shared component is out of scope. | Reads output ownership and blocks a forbidden side effect; it must not own LiveVoice state. | `LiveVoice-owned host integration segment`. | Hermes does not face this Jiuwen shared-UI collision. | **RETAIN HOST GUARD** until one unified output owner exists; then simplify the segment, never migrate the whole component. | Depends on `ttsOutputOwnership.ts`; negative UI tests must assert zero playback while fenced. High confidence. |

## 8. Audio/speech batch conclusion and remaining coverage

This batch finds no AgentCore downstream candidate inside audio, speech provider,
browser media or TTS ownership. Their line count is predominantly caused by
real media protocol, provider, browser lifecycle, failure and composition
boundaries. Slimming here therefore means removing the parallel legacy route,
retiring the unused realtime port, splitting concentrated owners without
duplicating authority, and consolidating speech/text contracts—not moving voice
code into AgentCore.

The remaining inventory still requires the same semantic treatment for Agent
bridge, Task/Executor, persistence/durability, observability, product
composition, frontend UI/presentation, shared host segments and support assets.
No migration or deletion is authorized by the dispositions above.

## 9. Agent Bridge and Conversation Runtime dispositions

The Agent path must keep three authorities separate:

1. AgentCore owns generic Agent execution and streaming through public
   `Runner.run_agent` / `Runner.run_agent_streaming` and `BaseAgent` invocation.
2. JiuwenSwarm's Agent facade owns the narrow SDK/backend adaptation and its
   no-history isolated execution path.
3. LiveVoice owns committed-turn admission, formal context, response generation,
   presentation, history eligibility, barge-in and product cleanup.

Treating all three as one “Agent bridge” is a major reason the current code is
hard to explain. It is not evidence that all three belong in AgentCore.

| Module or segment / representative public symbols | Capability domain; responsibility and necessity | State authority | AgentCore relation | Hermes comparison | Size driver and proposed disposition | Dependencies, evidence, confidence |
|---|---|---|---|---|---|---|
| `jiuwenswarm/server/live_voice/agent_bridge.py`<br>`AgentBridgePort`, `AgentRequest`, `AgentEvent` | **Agent Bridge / legacy compatibility.** The old port runs a committed turn in a private thread pool; `AgentEvent` remains the value projected by the current formal path. | The port owns only ephemeral futures/fingerprints; event identity is LiveVoice round provenance. | `AgentBridgePort` is **DIRECT REUSE / BASE EXISTING** through AgentCore `Runner.run_agent_streaming` or `BaseAgent.stream`; `AgentEvent` remains LiveVoice-owned. | Partial analogue to Hermes' Agent/session connection; the private worker pool is not a required voice abstraction. | No production caller imports `AgentBridgePort`; **SPLIT** `AgentEvent` into the formal bridge contract, port its useful close/provenance tests, then **REMOVE AFTER GATE** the thread-pool port. | Only `fake_verticals.py` references the port; current runtime imports the event value. High confidence. |
| `jiuwenswarm/server/live_voice/agent_bridge_runtime.py`<br>`AgentBridgeRuntime`, `AgentBridgeDispatchReservation`, `AgentRoundRequest`, delivery/completion values | **Agent Bridge / Conversation Runtime.** Reserves one committed round, delegates a real Agent stream and projects response/progress delivery with exact provenance. | Owns LiveVoice round admission, response-generation delivery and ephemeral queues; Agent execution remains downstream. | **ADAPTER REUSE** for invocation (`BRIDGE-02`) plus `LIVEVOICE_KEEP` for response completion/delivery (`BRIDGE-03`). No generic Agent execution state should remain here. | Combines Hermes' Agent connection and voice-session event projection roles, with stricter Jiuwen identity and rollback fencing. | Admission, adapter invocation, delivery queue and completion are concentrated; **SPLIT** the thin Agent invocation adapter from LiveVoice delivery/completion while retaining one round authority. | Consumed by `AgentConversationRuntime`; reserve/commit/abort/rollback/close/provenance tests are the oracle. High confidence. |
| `jiuwenswarm/server/live_voice/jiuwenswarm_agent_adapter.py`<br>`JiuWenSwarmAgentAdapter.stream` | **Agent Bridge.** Converts an already-authorized Harness stream into provenance-bound LiveVoice Agent events without changing Harness lifecycle envelopes. | Stateless projection around one trusted `HarnessRoundHandle`; no execution or conversation authority. | **ADAPTER REUSE** of the existing Agent/Runner stream. This is the intended thin downstream layer, not an AgentCore PR candidate. | Same boundary as a Hermes Agent/session stream adapter, with Jiuwen event validation. | Already narrow; **RETAIN AS THIN ADAPTER**, optionally co-locate event conversion with the extracted bridge adapter. | Requires exact handle/request/round/response/correlation binding; adapter stream tests apply. High confidence. |
| `jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py`<br>`JiuWenSwarmRoundHarness`, `HarnessRoundReservation`, `HarnessRoundHandle`, `FormalAgentFacade` | **Agent Bridge / Conversation Runtime.** Provides reserve/commit/cancel/close semantics around one formal Jiuwen Agent stream and protects delivery capacity. | Owns product round reservation, handle lifecycle and bounded delivery; the facade owns actual Agent execution. | **ADAPTER REUSE** of the Agent facade/AgentCore stream. Reservation and response binding are LiveVoice-owned and must not be replaced by background Task truth. | Partial analogue to Hermes voice-session Agent connection; Jiuwen adds explicit two-phase admission, exact cancel and delivery fencing. | Reservation state, handle queues, stream validation and cleanup are combined; **SPLIT** pure binding/validation and queue helpers while preserving the single Harness round owner. | Called by `AgentConversationRuntime`; round admission/final/cancel/cleanup tests are required. High confidence. |
| `jiuwenswarm/server/runtime/agent_adapter/formal_live_voice.py`<br>`FormalContextEntry`, `FormalContextSnapshot`, `FormalAgentExecution` | **Agent Bridge / Conversation Runtime.** Immutable carrier for the committed text, selected context, isolated session and per-round tool policy passed to Jiuwen's Agent facade. | Contract only; LiveVoice selects context and the facade executes it. | **ADAPTER REUSE**: maps product-owned commitment/context to existing Agent execution. These LiveVoice value types do not belong in AgentCore. | Partial analogue to Hermes Agent-session input construction; Jiuwen retains explicit commit/context provenance. | Focused module; **RETAIN AS FORMAL CARRIER** and keep it free of execution/history state. | Used by the round harness, facade and product composition; context scope/duplicate/commit tests apply. High confidence. |
| LiveVoice segment of `jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py`<br>`FormalLiveVoiceAgentAdapter.process_formal_live_voice_stream_impl` | **Agent Bridge / shared SDK adapter contract.** Declares the optional lower-adapter capability used by the formal no-history route. | Protocol only. | **ADAPTER REUSE** boundary above AgentCore-backed SDK implementations; no downstream migration. | No separate Hermes owner is needed. | Already minimal; **RETAIN AS OPTIONAL PROTOCOL** until a broader Jiuwen execution-options contract legitimately subsumes it. | Implemented by the Harness/Deep adapter and capability-probed by the facade. High confidence. |
| LiveVoice segment of `jiuwenswarm/server/runtime/agent_adapter/interface.py`<br>`supports_formal_live_voice`, `process_formal_live_voice_stream` | **Agent Bridge / shared facade.** Validates capability, builds an isolated no-memory request and delegates exactly one lower Agent stream. | Owns adapter selection and request translation only; no conversation, presentation or Task state. | **ADAPTER REUSE** of existing Agent execution. This is the correct JiuwenSwarm-to-AgentCore boundary. | Partial analogue to Hermes Agent connection/configuration, but Jiuwen must isolate shared Chat history and tools. | The segment is bounded inside a large shared facade; **RETAIN**, with possible extraction of pure formal request construction to the carrier module. | Calls only the optional lower-adapter seam; facade unit/integration tests are evidence. High confidence. |
| LiveVoice segment of `jiuwenswarm/server/runtime/agent_adapter/interface_deep.py`<br>`process_formal_live_voice_stream_impl` | **Agent Bridge / shared Harness backend.** Runs an isolated ordinary-Agent session while excluding slash/Goal/Team/AutoHarness/A2UI/debug/history paths and enforcing exact event/tool policy. | Owns lower-adapter session execution and cleanup; LiveVoice owns round authority. | **ADAPTER REUSE** over the AgentCore-backed DeepAgent/Agent stream; product exclusion policy stays in JiuwenSwarm. | Hermes' direct Agent-session loop is simpler because it does not share Jiuwen's broad Chat orchestration host. | Much apparent size belongs to the shared Deep adapter, not LiveVoice. **EXTRACT/REFACTOR ONLY THE FORMAL SEGMENT** into a dedicated helper if this reduces coupling; never count or move the whole host file. | Called only through the formal facade; allowed-event, tool-denial, cleanup and no-history tests are mandatory. High confidence. |
| LiveVoice segment of `jiuwenswarm/server/runtime/session/session_history.py`<br>`register_formal_no_history_session`, `unregister_formal_no_history_session`, formal history guard | **Agent Bridge / product history safety.** Defensive fence preventing the isolated formal Agent session from writing shared Chat history; formal history is written later only from committed/adopted LiveVoice facts. | Owns a process-local no-history registration guard, not product history truth. | `LiveVoice-owned host integration`; AgentCore session persistence cannot decide Jiuwen product adoption. | Hermes does not need this shared-Chat collision fence. | Compatibility fence exists because the lower adapter shares history machinery; **RETAIN UNTIL GATE**, then consolidate when the formal execution seam structurally cannot reach implicit history. | Paired with Deep-adapter registration/cleanup and `formal_history_writer.py`; negative tests must prove zero implicit history. High confidence. |
| `jiuwenswarm/server/live_voice/conversation_runtime.py`<br>`ConversationRuntime`, `ConversationSnapshot`, `RuntimeEvent`, `RuntimeEffect` | **Conversation Runtime.** Pure synchronous state machine for interaction, turn, response, cancellation and output-effect transitions. | Canonical in-memory LiveVoice conversation state for one runtime; no AgentCore Task authority. | `LIVEVOICE_KEEP`; AgentCore Runner/Task components must not own voice turn or playout state. | Direct analogue to Hermes' voice-session/generation state, with explicit Jiuwen commit/cancel/effect values. | Already separates pure transitions from async orchestration; **RETAIN**, and consolidate duplicate identity/value types only through the canonical LiveVoice contract. | Wrapped by `ConversationRuntimeLoop`; state-transition and fingerprint tests apply. High confidence. |
| `jiuwenswarm/server/live_voice/conversation_runtime_loop.py`<br>`ConversationRuntimeLoop`, `ConversationEffect`, `PresentationHistoryIntent` | **Conversation Runtime / Realtime Media / Presentation.** Serializes runtime mutations and coordinates output, presentation ACK/history eligibility, barge-in and side-effect claims. | Single async owner for LiveVoice response/presentation lifecycle and emitted effects. | `LIVEVOICE_KEEP`; generic Agent execution is only an input and AgentCore cursor/effect truth must not replace voice playout authority. | Analogue to Hermes generation/playout interruption loop, with additional explicit ACK/history and effect fencing. | Async serialization, presentation/history, barge-in and effect projection are concentrated; **SPLIT** pure projection/history-policy helpers while keeping one mutation loop. | Used by `AgentConversationRuntime`; barge-in, cancel, stale ACK, history and close tests are the oracle. High confidence. |
| `jiuwenswarm/server/live_voice/agent_conversation_runtime.py`<br>`AgentConversationRuntime`, notification/effect/presentation handles | **Conversation Runtime / Agent Bridge / Presentation.** Current formal composition owner for committed turns, selected context, Agent rounds, Task-derived presentations, notification leases, effects, history, cancellation and shutdown. | Canonical LiveVoice foreground response/presentation authority; delegates Agent execution and background Task truth. | Predominantly `LIVEVOICE_KEEP`; only the Agent invocation seam is **ADAPTER REUSE**. It must consume—not duplicate—future AgentCore Task/event/effect APIs. | Main analogue to Hermes' voice-session loop, but Jiuwen adds Task presentation isolation, committed input, consumer leases, ACK and fail-closed history/effect rules. | The largest size driver is accumulation of several subordinate lifecycles under one authority; **SPLIT** formal context, notification lease, presentation/effect and history coordinators behind the same owner, without creating peer state machines. | Composed by `product_composition_registry.py`; broad committed-input, Agent, progress, ACK/history, barge-in, effect and shutdown tests are mandatory. High confidence. |

## 10. Agent/Conversation batch conclusion

This batch confirms one directly replaceable duplicate: the unused
`AgentBridgePort` thread-pool wrapper. The current production Agent path already
has the intended architecture—LiveVoice owns committed round semantics,
JiuwenSwarm adapts the isolated formal call, and the existing Agent/Runner owns
execution. No new AgentCore PR candidate is justified by these modules.

Most of the roughly 8,300 physical lines across the eight dedicated/formal
Agent and Conversation modules in this batch are not a second generic Agent
implementation. They encode LiveVoice round admission,
provenance, response/presentation authority, interruption, history eligibility,
bounded delivery and cleanup. The credible slimming path is to remove the old
thread-pool lane and split subordinate coordinators behind one Conversation
Runtime authority. No migration, deletion or production refactor is performed
by this preparation record.

## 11. Task, Executor and Durability dispositions

Hermes does not implement a durable, scoped, multi-Task authority comparable to
the current LiveVoice P3 Store/Core. Its absence explains why Hermes is much
smaller in this domain, but it cannot be used as evidence that Jiuwen should
drop command replay, attempts, outbox, event/cursor, result, checkpoint or
effect truth. The slimming question is instead which generic owners must become
AgentCore APIs and which product adapters remain in JiuwenSwarm.

### 11.1 Task, Store and event transport

| Module / representative public symbols | Capability domain; responsibility and necessity | State authority | AgentCore relation | Hermes comparison | Size driver and proposed disposition | Dependencies, evidence, confidence |
|---|---|---|---|---|---|---|
| `jiuwenswarm/server/live_voice/task_core.py`<br>`TaskCore`, `TaskRecord`, `AttemptRecord`, `TaskCommand`, `TaskEvent` | **Task Control Core / legacy reference.** Pure in-memory Task/Attempt transition, command replay and event model retained beside the persistent production path. | Test/demo memory authority only; production P3 uses the persistent Store/Core. | Generic transitions are replaceable by the local AgentCore A2/Scope candidates; command/event gaps belong to `ADD-01/02`. This is **PR-candidate replacement**, not current upstream direct reuse. | No Hermes analogue; Hermes session/Agent state is not durable Task truth. | A complete parallel model is the size driver; port unique oracles to AgentCore conformance, then **REMOVE AFTER GATE** rather than maintain a third state machine. | `voice_task_bridge.py`/fakes still carry legacy dependencies; positive transitions, conflict, cancel and event tests must migrate first. High confidence. |
| `jiuwenswarm/server/live_voice/formal_task_models.py`<br>formal Task/Attempt, command/precondition, result, event/cursor, outbox and executor-observation values | **Task Core / Executor / Event / Durability contracts.** Aggregates the complete P3 durable value model and validation vocabulary. | Values only, but they encode the schema consumed by every current persistent authority. | **MIXED PR CANDIDATE + ADAPTER**: generic scope/execution relation maps to local Scope/A2; command/result, outbox/event, cursor and checkpoint references require `ADD-01/02/03/05`; product operation/artifact/display vocabulary stays downstream. | No useful Hermes analogue beyond small session event values. | One file accumulates several independent bounded contexts; **SPLIT BY TARGET CONTRACT** and later delete generic duplicates only after AgentCore APIs land. Never copy the whole schema upstream. | Imported throughout Store/Core/composition and covered indirectly by the full P3 authority suite. High confidence on split; exact AgentCore package ownership follows each PR design. |
| `jiuwenswarm/server/live_voice/task_store.py`<br>`SqliteTaskStore`, `TaskOutboxDiagnosticFact`, `TaskDurabilityDiagnosticSnapshot` | **Task Control Core / Executor & Durability / Event.** Current schema-v6 SQLite authority for Task, Attempt, Command, Event, Outbox, Result, Cursor, Checkpoint and Effect facts. | Canonical current P3 durable authority and transaction owner. | **ADAPTER-DOWNSTREAM CUTOVER TARGET**: local Scope/A2 plus `ADD-01..05` must become the sole generic AgentCore authority. The old Store itself is not an AgentCore PR payload. | Hermes has no durable Task/effect/cursor store; its smaller state model cannot satisfy these invariants. | The very large module contains many real authorities because they share one transaction boundary, plus six-version migration/verification. **REPLACE AFTER GATE** with one AgentCore facade; retain only a read-only, version-checked future importer/rollback reader. | Entire persistent P3 suite, corruption/reopen/replay/concurrency and zero-effect tests are migration oracles. High confidence on ownership; physical import/rollback remains separately undecided. |
| `jiuwenswarm/server/live_voice/persistent_task_core.py`<br>`PersistentTaskCore`, `FormalExecutor`, `project_task_event` | **Task Control Core / Executor orchestration.** Routes commands through Store authority, drains durable outbox, invokes the executor and reconciles observations/recovery. | Orchestration owner over the LiveVoice Store; it should not remain a peer Task authority after cutover. | **ADAPTER REUSE AFTER PRs**: replace Store/Core operations with the AgentCore Task/dispatch/event/effect facade; retain only product command/executor/result translation. | No Hermes analogue; Hermes' foreground Agent loop does not provide durable background Task orchestration. | Command routing, dispatch, reconciliation and projection are combined because the Store is local; **REPLACE/SHRINK TO THIN PRODUCT FACADE** after Scope/A2 and `ADD-01..05`. | Depends on Store, executor and recovery contracts; outbox/reconcile/terminal/retry tests are required. High confidence. |
| `jiuwenswarm/server/live_voice/task_event_subscription.py`<br>`TaskEventSubscription`, `TaskEventSource`, `TaskEventAuthoritySource` | **Task Event delivery.** Establishes an authorized atomic baseline, replays to head, tails bounded batches with backpressure and closes safely. | Runtime queue/subscription state only; the source owns durable events. | **ADAPTER REUSE** over the future AgentCore `ADD-02` event reader. Whether AgentCore exposes a polling helper is packaging, not a new durable authority. | Partial analogue to Hermes stream consumption, but Hermes has no scoped durable replay/head contract. | Transport/race logic is substantial but legitimate; **RETAIN AS THIN SUBSCRIPTION ADAPTER** and remove any product-specific source duplication once AgentCore is canonical. | Event source/auth/baseline/replay/backpressure/close tests remain oracles. Medium-high confidence; final async API shape is open. |

### 11.2 Executor and durability

| Module / representative public symbols | Capability domain; responsibility and necessity | State authority | AgentCore relation | Hermes comparison | Size driver and proposed disposition | Dependencies, evidence, confidence |
|---|---|---|---|---|---|---|
| `jiuwenswarm/server/live_voice/executor_port.py`<br>`ExecutorPort`, `ExecutorState`, `ExecutorStatus`, `ExecutorCapabilities` | **Executor / legacy reference.** In-memory dispatch/start/cancel/finish model plus a small capability query. | Test/reference attempt state only; not the persistent production owner. | State transitions are replaced by local AgentCore A2/A1 candidates; capability selection remains a downstream adapter. **PR-candidate replacement**, not base direct reuse today. | Partial analogue to Hermes Agent-run lifecycle, without Hermes providing durable attempt truth. | Parallel state model adds little production value; **SPLIT** capability contract if still needed, port transition oracles, then **REMOVE AFTER GATE** the state machine. | Executor-port and Task transition/cancel tests must pass against AgentCore candidates. High confidence. |
| `jiuwenswarm/server/live_voice/executor_capabilities.py`<br>`ExecutorCapabilityProfile`, `TaskExecutionRequirements`, `ExecutorSelection`, `select_executor` | **Executor capability/configuration.** Canonicalizes Jiuwen D0/D1/D2/project capabilities, matches Task requirements and freezes the selected digest. | Pure selection/configuration result; AgentCore execution row must own the accepted opaque digest/generation. | **ADAPTER REUSE** of A2 `profile_digest`/generation. Current D0/D1/D2 and project vocabulary is product policy and should not be moved upstream. | No Hermes analogue is required; Hermes provider/config selection addresses a different layer. | Focused pure policy; **RETAIN/CONSOLIDATE** with configuration declaration, keeping output as an opaque AgentCore admission digest. | Capability-selection, mismatch-zero-launch and carrier integration tests apply. High confidence. |
| `jiuwenswarm/server/live_voice/project_code_executor.py`<br>`DirectProjectCodeExecutorAdapter`, `ProjectCodeExecutorAdapter`, `ProjectExecutionBinding` | **Executor & Durability / project adapter.** Combines durable attempt journal, live worker lifecycle, real background Agent stream, result/adjustment settlement, per-attempt worktree/patch safety, cleanup and D2 project-effect adaptation. | Currently owns duplicate generic attempt/lease/terminal/effect state plus legitimate project filesystem resources. | **MIXED**: attempt journal → A2 PR candidate; worker lifecycle → A1 PR candidate; immutable result → `ADD-01`; generic effect journal → `ADD-04`; Agent launch is Adapter reuse; project/worktree/patch/probe/cleanup is `LIVEVOICE_KEEP`. | Hermes only partially mirrors Agent launch/cancel; it has no durable project Task, worktree or effect reconciliation owner. | Several independent owners accumulated in one large module; **SPLIT** generic journals/lifecycle from retained project adapter. Retire `ProjectCodeExecutorAdapter` compatibility lane after Direct acceptance and caller audit. | Highest-risk boundary: requires real Agent, cancellation/quiescence, worktree/symlink/patch, result and D2 crash-window tests. High confidence on ownership split. |
| `jiuwenswarm/server/live_voice/durability_authority.py`<br>`DurabilityMutationAuthorization`, authorization mint/digest helpers | **D2 durability authority.** Defines the token that permits one verified continuation to mutate/settle a durable effect chain. | Generic mutation authorization value; current minting is tied to LiveVoice Store validation. | **AGENTCORE PR CANDIDATE `ADD-04`**. The future AgentCore EffectJournal/TaskDao boundary must mint it; LiveVoice may only consume/map it. | No Hermes analogue; process-local interrupt state cannot replace durable mutation authority. | Focused generic module; prepare it as part of the coherent EffectJournal PR, not as a standalone copied file. **RE-HOME GENERIC CONTRACT** after owner/API design. | Stale/forged/mismatched authorization must cause zero Tool/file/effect mutation. Medium-high confidence; TaskDao-vs-subordinate EffectDao placement remains open. |
| `jiuwenswarm/server/live_voice/durability_checkpoint.py`<br>`D1Checkpoint` | **D1 checkpoint/recovery.** Canonical opaque checkpoint fact bound to scope, profile, generation, sequence and digest. | Authority-free payload fact; current Store controls sequence and recovery authority. | **MIXED `ADD-05` PR + ADAPTER**: AgentCore needs token/version-fenced `ExecutionCheckpointRef`; Jiuwen keeps project checkpoint encoding/profile mapping. | No Hermes analogue; Hermes conversation/session state is not resumable background execution authority. | **SPLIT** generic authoritative reference publication from Jiuwen checkpoint codec; do not make raw checkpoint bytes authoritative. | Prefix/corruption/profile/generation/crash-before/after-publish and zero-launch tests are required. Medium confidence pending storage topology. |
| `jiuwenswarm/server/live_voice/durability_effects.py`<br>effect binding/intent/dispatch/receipt/observation/settlement values and `decide_effect_reconciliation` | **D2 external effects.** Models the append-only effect lifecycle and deterministic retry/verify/compensate/unknown reconciliation decision. | Generic effect facts are authority-free; current Store sequence/lease/settlement is authoritative. | **AGENTCORE PR CANDIDATE `ADD-04`** for generic phases, journal and reconciliation. Product Tool probes/compensation stay downstream. | No Hermes analogue; its tool/interrupt loop lacks crash-safe external-effect settlement. | Mostly generic durable contract rather than voice policy; **MOVE AS DESIGNED PR CONTRACT**, not by copying file/schema wholesale, and leave only Jiuwen binding adapters. | Existing phase ordering, corruption, crash-window, ambiguous and stale-authorization tests plus non-Voice conformance. Medium confidence; transaction owner/API topology remains open. |
| `jiuwenswarm/server/live_voice/durability_identity.py`<br>`DurabilityProfileBinding` | **Executor/Durability identity.** Binds Jiuwen capability/profile version and digest used by checkpoint/effect evidence. | Immutable product-profile identity; no mutation authority. | **ADAPTER REUSE**: map Jiuwen profile identity to A2/`ADD-04/05` opaque profile/generation fields. Do not upstream D0/D1/D2 product vocabulary. | No Hermes analogue is needed. | Already focused; **RETAIN AS PRODUCT MAPPING** or consolidate into executor capability configuration after AgentCore contracts stabilize. | Profile mismatch must reject resume/effect continuation with zero side effect. High confidence. |
| `jiuwenswarm/server/live_voice/durability_readers.py`<br>`DurabilityReadBinding`, `VerifiedCheckpointPrefix`, `VerifiedEffectPrefix`, `verify_checkpoint_prefix`, `verify_effect_prefix` | **Executor/Durability recovery reads.** Validates bounded, ordered, digest-bound checkpoint/effect prefixes while making them explicitly authority-free. | Verified immutable evidence only; cannot authorize launch/mutation. | **ADAPTER REUSE** over AgentCore Checkpointer/EffectJournal readers; generic prefix invariants should be supplied with `ADD-04/05`, while Jiuwen scope/profile decoding remains local. | No Hermes analogue; local voice-session recovery has different guarantees. | **SPLIT/CONSOLIDATE** generic prefix verification with its AgentCore owner and retain a small Jiuwen binding decoder. | Duplicate/out-of-order/corrupt/digest/profile/generation tests and authority-false assertions apply. Medium confidence on final value names. |
| `jiuwenswarm/server/live_voice/durability_recovery_facts.py`<br>`ExecutorRecoveryFacts` | **Executor/Durability recovery projection.** Combines verified checkpoint/effect prefixes into bounded, immutable executor recovery evidence. | Derived authority-free facts only. | **ADAPTER REUSE**: derived Jiuwen recovery view over A2 plus `ADD-04/05`; actual continuation token must come from AgentCore authority. | No Hermes analogue. | Focused projection; **RETAIN AS DOWNSTREAM VIEW** or merge with the project executor recovery adapter once generic readers exist. | All `*_authority` false, corruption, lineage and stale-binding tests remain required. High confidence. |

## 12. Task/Executor/Durability batch conclusion

This is the first batch that produces concrete AgentCore PR work. The coherent
generic candidates are not one monolithic migration:

- local Scope/A1/A2 candidate cleanup for scoped Task/execution ownership and
  live worker lifecycle;
- `ADD-01` command replay plus terminal outcome/immutable result;
- `ADD-02` transactional dispatch plus ordered Task events;
- `ADD-03` consumer/channel cursor;
- `ADD-04` external-effect journal/reconciliation;
- `ADD-05` authoritative execution-checkpoint reference.

The future LiveVoice remainder is much smaller but non-zero: verified product
identity mapping, capability selection, real Agent/project binding, worktree and
patch safety, effect-specific probe/compensation, product result projection and
event subscription/presentation adapters. The existing Store/Core and generic
journals are replacement sources and conformance oracles, not files to merge
wholesale into either AgentCore or the moving feature branch.

## 13. Voice–Task, presentation and product-policy dispositions

AgentCore event/result/cursor APIs can supply canonical background Task facts.
They cannot decide that a particular response generation was rendered in the
DOM, audibly played, safe to interrupt foreground speech, eligible for Chat
history or derived from a committed voice turn. Those are separate product
facts and explain much of this batch's retained code.

| Module / representative public symbols | Capability domain; responsibility and necessity | State authority | AgentCore relation | Hermes comparison | Size driver and proposed disposition | Dependencies, evidence, confidence |
|---|---|---|---|---|---|---|
| `jiuwenswarm/server/live_voice/presentation_ledger.py`<br>`PresentationLedger`, `PresentationAck`, `TaskPresentationConsumptionOwner`, runtime/adoption receipts | **Conversation Runtime / Task presentation.** Fences text/voice surfaces by response generation, validates segment alignment and accepts only authentic DOM adoption or playout receipts before history/cursor effects. | Canonical product presentation and history-adoption truth; current Task consumer portion also calls the durable cursor owner. | `LIVEVOICE_KEEP` for presentation; **ADAPTER REUSE** of future `ADD-03 CursorStore.advance` after product receipt verification. | Partial analogue to Hermes playout/generation ownership, but Hermes lacks independent text/voice Task consumption receipts. | Response presentation and Task-event consumption share receipt validation; **RETAIN**, and split the thin cursor adapter from product presentation authority after `ADD-03`. | Cross-surface, stale-generation, forged/wrong-surface ACK, close and history tests are required. High confidence. |
| `jiuwenswarm/server/live_voice/progress_notification_arbiter.py`<br>`ProgressNotificationArbiter`, `ForegroundSnapshot`, notification/speech dispositions | **Voice–Task Bridge / Interaction Intelligence / Presentation.** Decides whether a background update is spoken, rendered, deferred, suppressed or advanced without projection under foreground/generation/backpressure facts. | Runtime product policy and pending delivery state; it must never own Task/event/cursor truth. | `LIVEVOICE_KEEP`; AgentCore events/cursors provide inputs and accept a verified ACK only. | Hermes interruption logic is a partial analogue, but it has no Jiuwen background-Task speech/text arbitration. | Large explicit state/disposition vocabulary encodes safety and negative paths; **SPLIT** pure decision rules from queue/ACK mechanics, not upstream ownership. | Foreground, speech-disabled, defer/backpressure, stale generation and zero-advance tests apply. High confidence. |
| `jiuwenswarm/server/live_voice/task_progress_return.py`<br>`TaskEventAuthorityProgressSource`, `TaskProgressProjection`, `TaskProgressReturnBridge` | **Voice–Task Bridge / Event projection / Presentation.** Reads authorized Task events, projects generic progress and routes it to text/voice policy with exact origin/generation binding. | Derived projection and runtime delivery lifecycle only. | **MIXED ADAPTER + LIVEVOICE KEEP**: event source/projection consumes `ADD-02/03`; speech/text delivery policy remains LiveVoice. | Partial analogue to Hermes stream-to-speech projection, extended for durable background Task origin/cursor semantics. | Generic source/projection and product delivery coexist; **SPLIT** the pure event-to-progress projector and AgentCore source adapter from the retained return bridge. | Projection/order/terminal/handoff/auth, voice/text delivery and no-projection advance tests are oracles. Medium-high confidence on the generic projection vocabulary. |
| `jiuwenswarm/server/live_voice/p2_response_generation_store.py`<br>`SqliteP2ResponseGenerationOwner` | **Conversation Runtime / durable generation fencing.** Allocates monotonic response generations across restart while bounding stored identity data with an exact cache plus collision-safe high-water fences. | Canonical product response-generation allocator; no Task/Agent execution authority. | `LIVEVOICE_KEEP`; AgentCore Task/execution generations describe a different lifecycle. | Hermes keeps generation/interruption state in the voice process but has no equivalent bounded durable Web response-generation owner. | Schema verification and bounded privacy/fence mechanics explain the size; **RETAIN**, with an optional later product-state storage consolidation only if the same authority/invariants remain. | Composed by authenticated/product registry paths; reopen/corruption/eviction/collision/monotonic tests apply. High confidence. |
| `jiuwenswarm/server/live_voice/voice_task_bridge.py`<br>`BoundedAlphaTaskIntentResolver`, `VoiceTaskBridge`, `ResolvedUnifiedCommittedInput` | **Voice–Task Bridge.** Routes only committed input to dialogue or explicit Task intent, resolves source spans/targets and prevents dialogue from acquiring Task authority. | Product semantic routing and target-resolution facts; no canonical Task state. | `LIVEVOICE_KEEP`; final explicit command uses the Scope/`ADD-01` adapter. | No direct Hermes analogue because Hermes does not expose Jiuwen's durable background Task control surface. | Production bridge and Alpha/demo itinerary heuristics coexist; **SPLIT/RETIRE** `BoundedAlphaTaskIntentResolver` hardcodes after production classifier acceptance while retaining the formal bridge. | Commit/replay, dialogue isolation, ambiguity/confirmation, target and zero-precommit-mutation tests apply. High confidence. |
| `jiuwenswarm/server/live_voice/voice_task_policy.py`<br>`FormalTaskPolicyAdapter`, `FormalTaskPolicyInput`, `FormalTaskInvocation` | **Voice–Task Bridge / product control policy.** Converts a resolved, confirmed product intent into the supported Task query/mutation invocation and rejects unsupported or stale operations. | Stateless product policy/translation; AgentCore owns the command result after invocation. | `LIVEVOICE_KEEP` as the downstream policy Adapter to Scope/`ADD-01`; D0/D1/D2/product command vocabulary must not move upstream implicitly. | No Hermes analogue. | Substantial operation-specific validation is intentional; **RETAIN/CONSOLIDATE** with the canonical product capability catalog to prevent duplicated allowlists. | Supported/unsupported/stale/confirmation and zero-effect policy tests apply. High confidence. |
| `jiuwenswarm/server/live_voice/production_task_classifier.py`<br>`ProductionTaskIntentClassifier`, `ProductionTaskIntentClassifierContext` | **Voice–Task Bridge / Interaction Intelligence.** Parses structured input and classifies natural committed text into product Task proposals without mutating anything. | Stateless semantic proposal only. | `LIVEVOICE_KEEP`; AgentCore accepts an explicit command and should not interpret product conversation language. | Hermes intent routing is at most a loose analogue; parity is neither required nor desired. | **RETAIN** as a pure classifier; continue separating classification from authority/confirmation and generalize beyond recorded demo grammar through product tests. | Structured/natural/prefixed/ambiguous/ordinary-dialogue corpus is the oracle. High confidence. |
| `jiuwenswarm/server/live_voice/production_task_intent.py`<br>`ProductionMultiTaskResolver`, `BoundedClarificationOwner`, authenticated fact/origin/confirmation/proposal values | **Voice–Task Bridge / product intent resolution.** Revalidates Task facts, binds trusted committed origin, extracts fields, resolves among multiple Tasks and owns bounded clarification/confirmation continuation. | Product proposal, clarification and one-shot confirmation authority; canonical Task truth stays downstream. | `LIVEVOICE_KEEP`; read-only AgentCore Task facts are inputs and only a resolved confirmed command crosses Scope/`ADD-01`. | No Hermes analogue for this Jiuwen product workflow. | Schemas, origin receipts, clarification owner and resolver are concentrated; **SPLIT** immutable schemas/origin verification from resolver state if this lowers coupling, preserving one product decision owner. | Multi-Task target, stale fact, origin, clarification, confirmation replay and zero-effect tests apply. High confidence. |
| `jiuwenswarm/server/live_voice/unified_committed_input.py`<br>`SqliteUnifiedCommittedInputJournal`, `UnifiedInputAdmission`, `UnifiedForegroundEffectAdmission` | **Conversation Runtime / Voice–Task Bridge.** Idempotently admits one committed input and recovers foreground response effects without conflating them with background Task execution. | Durable product committed-input and foreground-effect authority. | `LIVEVOICE_KEEP`; AgentCore command/effect ledgers must not decide voice/text commitment or foreground response presentation. | Partial analogue to Hermes committed-turn state, with stronger restart/idempotency fencing. | Input admission and foreground-effect recovery share product identity/storage; **RETAIN**, with a possible internal split only if atomic idempotency is preserved. | Commit conflict/replay, lease/renew/recovery and zero duplicate foreground-effect tests apply. High confidence. |
| `jiuwenswarm/server/live_voice/formal_history_writer.py`<br>`SessionFormalHistoryWriter.persist_user`, `persist_assistant` | **Conversation Runtime / product history.** Thin side-effect adapter that writes committed user text and assistant text only after authentic text-surface adoption. | Product session-history side effect; never Task/result/event/effect truth. | `LIVEVOICE_KEEP`; AgentCore Session/VCS cannot decide LiveVoice commitment or DOM adoption eligibility. | Partial analogue to Hermes conversation history writer, with explicit Jiuwen presentation gate. | Already narrow; **RETAIN AS THIN ADAPTER**. | Negative tests must prove no history for uncommitted, stale, failed, voice-only or unacknowledged text. High confidence. |
| `jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py`<br>`ProductP2InteractionAdapter`, `P2ActivationLease`, activation/binding/cleanup values | **Interaction Intelligence / Conversation Runtime / product composition.** Authenticates and allocates one P2 runtime/Interaction Engine lease, delegates only explicit actions and coordinates presentation, barge-in, notifications and cleanup. | Product activation/lease authority; Interaction Engine outputs remain intentions and cannot mutate Agent/Tool/Task/history/media by themselves. | `LIVEVOICE_KEEP`; its Agent call uses the formal adapter and Task progress uses future AgentCore event/cursor adapters. | Main partial analogue is Hermes voice-session composition, but Jiuwen separates authenticated activation and effect authority more strictly. | Activation, lease facade, notification/presentation delegation and failed cleanup are concentrated; **SPLIT** activation allocation, lease delegation and cleanup coordinator behind one owner. | Authority-before-allocation, exact binding, forbidden-side-effect, presentation/barge-in and retained-cleanup tests are required. High confidence. |
| `jiuwenswarm/server/live_voice/product_p2_readiness.py`<br>`evaluate_product_p2_readiness`, readiness fact/result vocabulary | **Configuration / validation support.** Pure fail-closed evaluation of externally observed dependency facts; it explicitly grants no runtime or Gate evidence. | No runtime authority or discovery. | `LiveVoice-owned support`; no AgentCore relation. | No Hermes product analogue is needed. | No production caller exists; **RE-HOME TO VALIDATION SUPPORT** or remove after its oracle is adopted by the actual preflight owner. It should not remain counted as product runtime. | Only its unit tests import it. High confidence. |
| `jiuwenswarm/server/live_voice/product_p3_text_adapter.py`<br>`ProductP3TextAdapter`, `ProductP3ProgressCleanupHandle`, query/progress activation values | **Voice–Task Bridge / Integrated product composition.** Default-off trusted P3 query and text-progress seam that revalidates authority, activates an event source and retains cleanup/effect fencing. | Product route/query/progress activation and cleanup lifecycle; underlying Task/event/cursor authority is delegated. | **ADAPTER REUSE** of future Scope/Task/`ADD-02/03` APIs plus `LIVEVOICE_KEEP` for product authority, text/voice sinks and cleanup. | No direct Hermes analogue; this is Jiuwen durable Task-to-product presentation. | Query, progress activation and retained cleanup are combined; **SPLIT** AgentCore query/source adapters from product activation/cleanup while keeping default-off authority. | Authority revalidation, inactive paths, cleanup capacity, stale generation and sink-fencing tests apply. High confidence. |

## 14. Voice–Task/presentation batch conclusion

This batch produces no additional generic AgentCore PR beyond `ADD-01/02/03`.
It does define the future thin Jiuwen adapters that consume those APIs. Most of
the retained size exists because Task fact, product decision, response
generation, text adoption, voice playout and Chat history are deliberately
different truths.

The clearest near-term slimming candidates are preparation-only decisions:
retire the Alpha/demo intent resolver after production-language acceptance;
re-home the uncomposed P2 readiness evaluator to validation support; split pure
Task progress projection/source from speech policy; and keep cursor advancement
as a thin effect after authentic presentation receipt. No code is moved or
deleted while the LiveVoice feature branch is still advancing.
