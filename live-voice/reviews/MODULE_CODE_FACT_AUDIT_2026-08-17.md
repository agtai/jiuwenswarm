# Live Voice module code-fact audit — 2026-08-17

> Audit state: **COMPLETE**
>
> This is a read-only code-fact audit of the 15 capability/module rows in
> [STATUS](../STATUS.md), performed on the exact frozen source below. It
> records entrypoints/owners/call chains, formal versus legacy/Demo/flag-off
> routes, implemented behaviour, tests and missing oracles, hardcodes,
> duplicates, retirement gates, dependencies and a justified status. It does not
> modify product code, grant new module-completion credit, or replace the
> historical Integrated Web Alpha acceptance (still bound to
> `d33b520e0d21ae0829d30814d77a01cc18256f09`).

## 1. Audited source and Git state

- Repository: `C:\Users\admin\Desktop\live voice ds\0817_bugfix`
- Branch: `hx/0812_live_voice_w3`
- Upstream: `agtai/hx/0812_live_voice_w3`
- Remote `agtai`: `https://github.com/agtai/jiuwenswarm`
- Audited HEAD: `6e7e82d3bb4f8049e6692b5a56a8c3fbcb57ebb8`
- Local/upstream relation at freeze: **0 ahead / 0 behind**
- Worktree at freeze: **clean**

Product-code baseline: `6e7e82d3` is exactly one documentation-only commit
(`docs(live-voice): reconcile project status and handoff`) ahead of the last
assessed product-code baseline
`ca9a9d9a3be5f76c4feee980030a1b3ce065b9ab`. The `ca9a9d9a..6e7e82d3` diff touches
only `live-voice/*.md` and `scripts/live_voice/*.md` (52 files, no `.py`/`.ts`
product source), so **the audited product code equals `ca9a9d9a`**.

Relation to the Post-Alpha physical run: the Post-Alpha record
[POST_ALPHA_DEMO_20260817_95b26308_WORKTREE](../evidence/POST_ALPHA_DEMO_20260817_95b26308_WORKTREE.md)
was executed on a dirty working tree over baseline
`95b26308717b896d820f011defa691243cad58f8`. `95b26308` is the single direct
parent of `ca9a9d9a`; `ca9a9d9a` ("stabilize post-alpha demo flow") changed the
executor by only 3 lines (hardcoded task-name constant) and `voice_task_bridge.py`
by 17 lines (hardcoded task-name constant + inner-trip classification). The six
known blockers are therefore re-verified below against this clean source; the
Post-Alpha dirty-source observations are treated as runtime evidence that must be
re-checked, not as current code facts.

## 2. Method and exclusions

- Authority order applied: current source → current tests/test discovery →
  configuration/registration/composition → runtime call chain → accepted
  contract/decision → exact-source review → STATUS claims.
- One main session audited the four cross-cutting domains and the
  Identity/Authority/State/Cancel/Result/Recovery/Durability seams; three
  read-only subagents audited non-overlapping capability groups (P1/Media,
  P2/Integrated Web, P3/Authority).
- Exclusions: no product-code change, no Git history operation, no full
  historical document corpus load, no unfocused full-suite run, no credential/
  private-config/raw-audio capture. Fake/fixture/Demo/legacy paths are never
  credited as formal capability. Code presence is never completion credit.
- Focused tests: **none were run**. The six blockers were adjudicated by static
  source + test-source + the Post-Alpha runtime record; no static ambiguity
  required a dynamic run (see §14).

## 3. Models and reasoning strength

- Main session: `deepseek v4 pro`, reasoning effort `high`.
- Subagents inherit the main-session model/effort (the delegation tool exposes
  no per-subagent model/effort override), so all three ran `deepseek v4 pro` /
  `high`; none was downgraded. This matches the fallback clause of the audit
  prompt and is recorded here as the actual configuration.

## 4. Subagent scopes and return status

| Subagent | Scope | Domains | Returned | Result |
|---|---|---|---|---|
| P1 / Media | `6e94bddc-4883-47a1-942f-776efc696cf9` | Audio Device & browser I/O; Speech Recognition; Speech Synthesis; Realtime Media | yes | 4 × PARTIAL |
| P2 / Integrated Web | `476aa639-8ef4-499d-a055-8789525d52e5` | Conversation Runtime; Interaction Intelligence; Agent Bridge and dialogue truth; Integrated Web product experience | yes | 4 × PARTIAL |
| P3 / Authority | `5ec18cd4-96fc-4a72-bccb-e391f7fa63a9` | Task Control Core and Store; Executor & Durability; Voice–Task Bridge | yes | Task Core PARTIAL; Executor PARTIAL (down from BLOCKED); Bridge PARTIAL |

All three were read-only: no file writes, no Git operations, no test runs. Their
structured reports (file paths, symbols, call chains, tests, status evidence,
confidence, open issues) were re-verified by the main session (§5).

## 5. Unified 15-domain matrix

`COMPLETE` = implemented and accepted on identified source. `PARTIAL` = useful
implementation exists but required behaviour or evidence remains. `BLOCKED` = a
demonstrated defect prevents the positive journey. `NOT STARTED` = no accepted
current implementation boundary. `UNKNOWN` = evidence incomplete.

| # | Capability / module | Audit status | Matches STATUS? | Confidence |
|---|---|---|---|---|
| 1 | Audio Device & browser I/O | PARTIAL | yes | high |
| 2 | Speech Recognition | PARTIAL | yes | high |
| 3 | Speech Synthesis | PARTIAL | yes | high |
| 4 | Realtime Media | PARTIAL | yes | high |
| 5 | Conversation Runtime | PARTIAL | yes | high |
| 6 | Interaction Intelligence | PARTIAL | yes (ownership clarified, §6.6) | high |
| 7 | Agent Bridge and dialogue truth | PARTIAL | yes | high |
| 8 | Integrated Web product experience | PARTIAL | yes | high |
| 9 | Task Control Core and Store | PARTIAL | yes | high |
| 10 | Executor & Durability | PARTIAL | yes — re-scored from BLOCKED in this audit (§6.10) | high |
| 11 | Voice–Task Bridge | PARTIAL | yes | high |
| 12 | Observability, benchmark and latency | PARTIAL | yes | high |
| 13 | Automated verification and product acceptance | PARTIAL | yes | high |
| 14 | Configuration, code and document cleanup | PARTIAL | yes | high |
| 15 | Production operations | NOT STARTED (as a complete boundary) | yes | high |

The “Matches STATUS?” column compares each audit conclusion with the
post-audit reconciled `STATUS.md`. Executor & Durability was the only pre-audit
mismatch: this audit re-scored it from BLOCKED to PARTIAL, and `STATUS.md` was
updated accordingly.

## 6. Per-domain code facts

Each entry records: actual entrypoints/owners, path classification, implemented
behaviour, missing behaviour, status/authority facts, tests and missing oracles,
hardcodes, duplicates, removable content, cross-module dependencies, and the
justified status. Source references are repository-relative with symbols.

### 6.1 Audio Device & browser I/O — PARTIAL

- Entrypoints/owners: browser capture/playout lives in
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts`
  (`BrowserAudioIOAdapter`) and
  `formal/adapters/browserGatewayMediaTransport.ts`
  (`BrowserGatewayMediaTransport`); device enumeration in
  `formal/browserAudioDeviceSelection.ts`; the capture processor in
  `formal/adapters/liveVoiceCaptureProcessor.js`. The formal frontend
  composition root is `formal/productP1VoiceRoute.ts` `ProductP1VoiceRoute`,
  which constructs `BrowserAudioIOAdapter` (L334) and
  `createBrowserDedicatedMediaRoute` (L528/1115/1291).
- Path classification: formal path is flag-gated
  (`VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1`); legacy Demo hook
  `useLiveVoiceDemo`/`liveVoiceCore` remains constructed by
  `components/ChatPanel/index.tsx` (L1230) and is selected when the formal flag
  is off. `browserAudioDeviceSelection.ts` is present but not wired into the
  formal adapter (device/permission recovery is not the formal default route).
- Implemented: capture/playout lifecycle, dedicated media wiring, exact-response
  playout ACK (productP1VoiceRoute L1358–1453), bounded close.
- Missing: default formal device/permission recovery, AEC/NS/AGC/double-talk
  behaviour, measured first-frame/loss/stop targets; the evidence fields are
  hardcoded `false` in places.
- Tests: `tests/unit_tests/live_voice/test_realtime_media.py`,
  `test_speech_ports.py`, frontend
  `jiuwenswarm/channels/web/frontend/tests/liveVoiceBrowserAudioIOAdapter.test.mjs`,
  `liveVoiceCaptureProcessor.test.mjs`,
  `liveVoiceBrowserAudioDeviceSelection.test.mjs`,
  `liveVoiceBrowserDedicatedMediaRoute.test.mjs`.
- Status: PARTIAL (matches STATUS). Blockers: none directly; depends on P2 media
  runtime integration and the declared browser/device matrix.

### 6.2 Speech Recognition — PARTIAL

- Entrypoints/owners: `jiuwenswarm/server/live_voice/openai_streaming_speech.py`
  and `streaming_speech.py` (Streaming STT); `batch_speech.py` (Batch STT);
  gateway routes `jiuwenswarm/gateway/live_voice/streaming_speech_route.py` and
  `streaming_synthesis_route.py`; browser fallback in
  `formal/adapters/browserSpeechRecognitionAdapter.ts` (facade over the Web
  Speech API) and `formal/gatewayBatchSpeechClient.ts`.
- Implemented: controlled OpenAI Streaming/Batch STT with timeout/cancel, browser
  fallback, partial/final distinction.
- Missing: provider-neutral configuration, a fixed accuracy/latency corpus, robust
  fallback/cancel across broader device/network, and measured accuracy targets.
- Tests: `tests/unit_tests/live_voice/test_streaming_speech.py`,
  `test_batch_speech.py`, `test_openai_streaming_speech.py`; frontend
  `liveVoiceBrowserSpeechAdapters.test.mjs`, `liveVoiceGatewayBatchSpeech.test.mjs`.
- Status: PARTIAL (matches STATUS). Hardcode: Provider is OpenAI-bound today.

### 6.3 Speech Synthesis — PARTIAL

- Entrypoints/owners: gateway
  `jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py` (Streaming TTS
  bridge) and `jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py`;
  `jiuwenswarm/server/live_voice/batch_speech.py` (Batch TTS);
  browser playout via `browserSpeechSynthesisAdapter.ts`; playout ACK ownership in
  `productP1VoiceRoute.ts` (L1358–1453).
- Implemented: Streaming/Batch TTS, browser playout, response ownership and ACK.
- Missing: first-audio/underrun/pronunciation targets, complete stale/cancel
  recovery, provider-neutral configuration.
- Tests: `tests/unit_tests/live_voice/test_batch_speech.py` (timeout/cancel/
  terminal paths), `test_streaming_speech.py`; frontend
  `liveVoiceStreamingSpeech.test.mjs`, `liveVoiceTtsText.test.mjs`,
  `ttsOutputOwnership.test.mjs`.
- Status: PARTIAL (matches STATUS).

### 6.4 Realtime Media — PARTIAL

- Entrypoints/owners: dedicated media route
  `jiuwenswarm/gateway/live_voice/dedicated_media_route.py`,
  `dedicated_media_registration.py`,
  `browser_gateway_media_transport.py`; frontend
  `formal/adapters/browserDedicatedMediaRoute.ts`. `realtime_media.py`
  (`jiuwenswarm/server/live_voice/realtime_media.py`) is a foundation/
  simulation boundary that is **not composed into the current runtime** (per the
  branch-retirement audit and P1 verification) — its presence is not formal
  credit.
- Implemented: dedicated transport, media registration, receipts/ACK, bounded
  close.
- Missing: backpressure/load targets, drop/reorder/corruption/reconnect matrix,
  stable diagnostics across repeated recovery.
- Tests: `tests/unit_tests/live_voice/test_realtime_media.py`; frontend
  `liveVoiceBrowserGatewayMediaTransport.test.mjs`,
  `liveVoiceBrowserDedicatedMediaRoute.test.mjs`.
- Status: PARTIAL (matches STATUS). Realtime Media is a named seam whose
  composition owner must be confirmed (P1 raised `realtime_media.py` non-wiring).

### 6.5 Conversation Runtime — PARTIAL

- Entrypoints/owners: `jiuwenswarm/server/live_voice/conversation_runtime.py` and
  `conversation_runtime_loop.py` (runtime loop with committed-input fencing,
  generation ownership, ACK/history projection, Exit fencing, playout-time
  barge-in); the formal runtime replica
  `formal/conversationRuntimeReplica.ts`; committed input
  `unified_committed_input.py` (`UnifiedCommittedInputOwner`, recovery_json
  durability). Runtime correlation enters at
  `agent_conversation_runtime.py` (correlation_id throughout); the older
  `conversation_runtime.py`/`conversation_runtime_loop.py` carry no correlation.
- Implemented: committed-input fencing, generation ownership, ACK/history,
  Exit fencing, playout-time barge-in.
- Missing: interruption during Agent generation, complete `ask_user` voice loop,
  cross-load arbitration, recovery without repeated ambiguous state.
- Tests: `tests/unit_tests/live_voice/test_conversation_runtime.py`,
  `test_conversation_runtime_loop.py`, `test_agent_conversation_runtime.py`,
  `test_unified_committed_input.py`; frontend
  `liveVoiceConversationRuntime.test.mjs`, `liveVoiceTurnLifecycle.test.mjs`,
  `liveVoiceMessageGate.test.mjs`.
- Status: PARTIAL (matches STATUS).

### 6.6 Interaction Intelligence — PARTIAL (ownership clarified)

- Entrypoints/owners: `jiuwenswarm/server/live_voice/interaction_engine.py` is a
  contract/Port surface (per P2 it is a contract fake, not the runtime owner).
  VAD/EOT live in the speech modules; dialogue/background routing lives in
  `voice_task_bridge.py` (`resolve_unified` and the `_UNIFIED_*` patterns). This
  is a cross-module ownership clarification: the STATUS row's "Interaction
  Intelligence" behaviour is currently split across Speech, `voice_task_bridge`
  and the registry, not owned by `interaction_engine.py`.
- Implemented: bounded VAD/EOT and dialogue/background routing for the controlled
  journey.
- Missing: general natural-language routing, false endpoint/interruption and
  echo/double-talk evaluation, language/config generalization.
- Tests: `tests/unit_tests/live_voice/test_interaction_engine.py` (contract),
  `test_voice_task_bridge.py` (routing), `test_formal_task_policy.py`.
- Status: PARTIAL (matches STATUS, but the ownership boundary needs the main
  session's clarification recorded here).

### 6.7 Agent Bridge and dialogue truth — PARTIAL

- Entrypoints/owners: `jiuwenswarm/server/live_voice/agent_bridge.py`,
  `agent_bridge_runtime.py`, `agent_conversation_runtime.py`,
  `jiuwenswarm_agent_adapter.py`, `jiuwenswarm_round_harness.py`,
  `p2_response_generation_store.py`, `progress_notification_arbiter.py`,
  `task_progress_return.py`. Dialogue truth isolation is enforced in the
  registry (`product_composition_registry.py`) and
  `voice_task_bridge.py` (DIALOGUE route rejects Task authority, L1154–1169).
- Implemented: real Agent dialogue/tools, bounded response/progress integration,
  five-layer Task-truth isolation (see Blocker 4, §7).
- Missing: non-blocking progress provenance, bounded result-context reservation
  (Blocker 5), unconstrained reread prevention (partial).
- Tests: `test_agent_bridge.py`, `test_agent_bridge_runtime.py`,
  `test_agent_conversation_runtime.py`, `test_p2_response_generation_store.py`,
  `test_progress_notification_arbiter.py`, `test_task_progress_return.py`.
- Status: PARTIAL (matches STATUS).

### 6.8 Integrated Web product experience — PARTIAL

- Entrypoints/owners: frontend
  `formal/integratedWebRouteShell.ts` (`IntegratedWebRouteShell`),
  `formal/productWebActivation.ts`, `formal/productP2ActivationJournal.ts`,
  `formal/productP3TaskTargetJournal.ts`,
  `formal/productP3ProgressGenerationJournal.ts`,
  `formal/productTextProgress.ts`, `formal/webPlatformDiagnostics.ts`, and the
  mounted panel `components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`.
- Path classification: `IntegratedWebRouteShell.activate()` is **never called**;
  only `.preview()` runs (P2). Composition is default-off with five environment
  flags (master `PRODUCT_COMPOSITION_ENABLE_ENV`, plus P2/P3 text/P3 mutation/
  critical-input/demo-policy-bypass) and frontend
  `.env.production` defaults `VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB=true`,
  `VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1=true`,
  `VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION=true`; the legacy
  `useLiveVoiceDemo` fallback remains constructed in `ChatPanel/index.tsx`
  (L1230, L1365). `formal/fakeP1Vertical.ts` and
  `formal/conversationRuntimeReplica.ts` are test/support dead modules in the
  production tree.
- Implemented: one-click hands-free shell, formal route preview, progress, TTS,
  current Task presentation.
- Missing: formal route as the only supported default; truthful queued/running/
  terminal UX (Blocker 2 display layer); device/privacy/recovery UX; legacy
  hook/flags removal.
- Tests: frontend `liveVoiceIntegratedWebRouteShell.test.mjs`,
  `liveVoiceIntegratedRoutePanel.test.mjs`,
  `liveVoiceIntegratedRoutePanelMounted.test.mjs`, `productWebActivation.test.mjs`,
  `productP2ActivationJournal.test.mjs`, `productP3TaskTargetJournal.test.mjs`,
  `productP3ProgressGenerationJournal.test.mjs`, `productTextProgress.test.mjs`,
  `liveVoiceWebPlatformDiagnostics.test.mjs`.
- Status: PARTIAL (matches STATUS).

### 6.9 Task Control Core and Store — PARTIAL

- Entrypoints/owners: `jiuwenswarm/server/live_voice/persistent_task_core.py`
  (`PersistentTaskCore`), `task_store.py` (`SqliteTaskStore`, schema v3),
  `formal_task_models.py` (identity/schema), `task_event_subscription.py`;
  legacy `task_core.py` (`TaskCore`, in-memory) still consumed by
  `voice_task_bridge.py` (parallel models — see §11).
- Implemented: stable Task/Attempt/Event/Command IDs, SQLite schema v3 +
  migration, idempotency, outbox, results, adjustments, one-current-Task
  recovery, retry admission, zero-side-effect terminal fencing.
- Missing: multiple addressed Tasks, target disambiguation,
  `update/provide_input/pause/resume/reprioritize`, successor revision,
  replay/unread cursor, one canonical Task model.
- Tests: `test_persistent_task_core.py` (terminal fence, nul-result rejection,
  retry-readiness, zero effects), `test_task_core.py`,
  `test_task_event_subscription.py`, `test_formal_task_policy.py`.
- Status: PARTIAL (matches STATUS).

### 6.10 Executor & Durability — PARTIAL (down from BLOCKED)

- Entrypoints/owners: `jiuwenswarm/server/live_voice/project_code_executor.py`
  (`DirectProjectCodeExecutorAdapter` + `_DirectExecutorJournal`),
  `executor_port.py`; the authenticated composition wires the Direct executor in
  `p3_authenticated_composition.py` (L2869 `DirectProjectCodeExecutorAdapter`).
  `ProjectCodeExecutorAdapter` remains a covered compatibility/test path.
- Implemented and re-verified this audit: `_run_attempt` persists a terminal
  outcome on **every** path (success `COMPLETED`; cancel `CANCELLED`/
  `INTERRUPTED`; exception `FAILED`) via `_journal.finish`; `_heartbeat` stops
  renewing once the record is terminal; `status()` returns observations from the
  journal (recovering expired leases) and `PersistentTaskCore.reconcile`/
  `drain_outbox_once` propagate those observations to `apply_observations` →
  `task.terminal`. This is why P3 downgraded B1 (Blocker 1) and this audit
  concurs on the static evidence.
- Missing: D1 checkpoint and D2 reconciliation semantics, capability selection,
  bounded timeout/orphan handling beyond lease recovery. The Post-Alpha
  dirty-source observation of terminalization/lease renewal is recorded as a
  required clean re-verification, not as a confirmed defect on this source
  (§7 B1).
- Tests: `test_project_code_executor.py`,
  `test_executor_port.py`, `test_persistent_task_core.py`
  (terminal/retry/cancel/zero-effects, racing-cancel suppression),
  `test_p3_authenticated_composition.py` (reconciliation/retry/terminal replay).
- Status: PARTIAL. Rationale for the STATUS change: the demonstrated terminal
  truth path is statically closed and tested on this source; the remaining
  D1/D2/capability gaps are feature-complete scope, not a positive-journey
  blocker. The clean physical re-verification is the open condition.

### 6.11 Voice–Task Bridge — PARTIAL

- Entrypoints/owners: `jiuwenswarm/server/live_voice/voice_task_bridge.py`
  (`BoundedAlphaTaskIntentResolver`, `resolve`, `resolve_unified`),
  `voice_task_policy.py`; frontend `formal/formalTaskIntentRoute.ts`,
  `formal/formalTaskResultRoute.ts`, `formal/formalTaskControlLeaf.ts`.
- Implemented: natural-language create/status/adjust/result paths, durable
  adjustment delivery, confirmation/negation/cancel, exact-form rejection with
  zero mutation.
- Missing: general routing, explicit multi-Task targeting, full Task operations,
  text/voice parity, open clarification.
- Tests: `test_voice_task_bridge.py`, `test_formal_task_policy.py`; frontend
  `formalTaskIntentRoute.test.mjs`, `formalTaskResultRoute.test.mjs`,
  `formalTaskControlLeaf.test.mjs`.
- Status: PARTIAL (matches STATUS).

### 6.12 Observability, benchmark and latency — PARTIAL

- Entrypoints/owners: `jiuwenswarm/server/live_voice/observability.py`
  (`TraceBinding`, `RouteDescriptor`, `LiveVoiceObservation`,
  `LiveVoiceMetric`, `LiveVoiceObservabilityCollector`, semantic matrices,
  `observation_from_task_event/outbox`); `observability_exporter.py`
  (`LiveVoiceObservabilityExporterBuffer`, backpressure/close/worker);
  `product_observability_adapter.py` (lease/activation, feature-off no-op);
  `alpha_benchmark.py` (deterministic I/O-free summarizer, no acceptance credit);
  frontend `formal/liveVoiceObservability.ts`, `liveVoiceRouteTelemetry.ts`,
  `webLifecycleObservationRecorder.ts`, `webPlatformDiagnostics.ts`.
- Implemented: correlation primitives (`correlation_id`/`interaction_id`/
  `turn_id`/`response_id`/`response_generation`/`round_id`/`task_id`/
  `attempt_id`) + segment binding matrices + a bounded collector.
- Missing: the product observability adapter is package-only and **not composed**
  (no runtime caller); user-visible recovery is a single ambiguous label (see
  Blocker 6); `article` is undefined before measurement; p50/p95 need real-path
  evidence (the benchmark's failure coverage is intentionally unverified for
  I/O-free collection).
- Tests: `test_observability.py`, `test_observability_exporter.py`,
  `test_observability_fault_harness.py`, `test_alpha_benchmark.py`,
  `test_product_observability_adapter.py`; frontend
  `liveVoiceObservability.test.mjs`, `liveVoiceRouteTelemetry.test.mjs`,
  `liveVoiceWebLifecycleObservationRecorder.test.mjs`.
- Status: PARTIAL (matches STATUS).

### 6.13 Automated verification and product acceptance — PARTIAL

- Authorities: root `TESTING.md` (D-032/D-046/D-074), `pytest.ini`
  (`testpaths = tests`), `pyproject.toml`, `tests/README.md`;
  `live-voice/validation/PRODUCT_READINESS_ACCEPTANCE.md` (current candidate
  contract), `live-voice/demo/PRODUCT_READINESS_SHOWCASE.md` (human journey),
  `live-voice/runbooks/E2E_RUNBOOK.md`.
- Test discovery facts (this audit): backend
  `tests/unit_tests/live_voice/` holds 42 test modules against 55 backend
  live-voice source modules; frontend
  `jiuwenswarm/channels/web/frontend/tests/` holds ~41 live-voice
  `*.test.mjs` files driven by `node --test` scripts in
  `channels/web/frontend/package.json` (`test:live-voice-*`).
- Missing: fresh 15-domain code-fact audit (this document closes it), affected
  defect reruns, capability-owned test migration (old S7/S8 oracles), cumulative
  feature-complete matrix, one clean real Journey, competitor-gap review,
  independent deep review.
- Latest physical result: `COMPLETED — DEFECTS RECORDED` (not PASS) on a dirty
  source; no immutable PASS exists for the hands-free journey.
- Status: PARTIAL (matches STATUS).

### 6.14 Configuration, code and document cleanup — PARTIAL

- Authorities: `live-voice/reviews/CODE_DUPLICATION_AND_RETIREMENT_AUDIT_2026-08-17.md`,
  `BRANCH_CONTENT_RETIREMENT_AUDIT_2026-08-17.md`,
  `DOCUMENT_RETIREMENT_AUDIT_2026-08-17.md`.
- State: three audits are ANALYSIS COMPLETE; Document Batch A is complete
  (19 files); actual source/script removal, test re-homing, and Batches B/C are
  **NOT STARTED**.
- Confirmations this audit: `.env.production` defaults three Live Voice flags on;
  backend `demo_policy_bypass_enabled` (`PRODUCT_DEMO_POLICY_BYPASS_ENV`) and the
  legacy `useLiveVoiceDemo` lane remain; the itinerary/`itinerary.md`/port/bypass
  hardcodes remain; parallel Task models and Direct-vs-compatibility executors
  remain (see §11, §12).
- Status: PARTIAL (matches STATUS).

### 6.15 Production operations — NOT STARTED (as a complete boundary)

- Privacy/preflight/observability foundations exist:
  `jiuwenswarm/server/live_voice/critical_token_safety.py` (`CriticalTokenPolicy`,
  `CriticalTokenSafetyGate`, clarification + committed-route guard),
  `alpha_privacy_conformance.py` (synthetic-canary privacy checks across 19
  surfaces).
- Missing (complete boundary): production auth/tenancy, public deployment,
  SLO/retention, security operations, compatibility matrix, release/rollback.
- Tests: `test_critical_token_safety.py`, `test_alpha_privacy_conformance.py`.
- Status: NOT STARTED (as a complete boundary; matches STATUS).

## 7. Six known blockers — re-verified

Each blocker is confirmed, corrected, or negated against this clean source.

### B1 — Executor terminalization (Agent completion → validation → application → TaskResult → terminalization)

- Source: `jiuwenswarm/server/live_voice/project_code_executor.py`
  `DirectProjectCodeExecutorAdapter._run_attempt` (L2781–3210) → `_journal.finish`
  on every path; `_heartbeat` (L3212) stops when terminal; `status()` (L3409)
  returns `_delivery(record)` observations; `persistent_task_core.py`
  `drain_outbox_once` (L614–697) and `reconcile` (L706+) propagate observations
  via `store.complete_outbox`/`apply_observations` → `task.terminal`.
- Trigger path: Agent return → validation (git-head/symlink/support) →
  `reserve_completion` → `_apply_attempt_patch` → `seal_applied_result` →
  `_journal.finish`; exceptions → `_journal.finish(FAILED/INTERRUPTED/CANCELLED)`.
- Affected state: attempt terminal in the executor journal; task terminal via
  Task Core observation application; owner/lease via `_heartbeat`.
- Existing tests: `test_project_code_executor.py` terminal paths;
  `test_persistent_task_core.py` `test_executor_terminal_truth_suppresses_racing_cancel_side_effect`,
  nul-result-before-terminal-write, retry-requires-terminal.
- Missing tests: a clean physical end-to-end Agent-return→task.terminal run on
  immutable source.
- Verdict: **partially closed on this clean source (static + unit tests);
  clean re-verification required.** The Post-Alpha dirty-source "terminal not
  persisted / lease renewed" observation cannot be confirmed or denied on this
  source without a clean run. Risk: High. Owner: Executor & Durability.

### B2 — Admission truth (`EXECUTOR_PROJECT_BUSY` accepted Task described as running)

- Source: `project_code_executor.py` `_DirectExecutorJournal` dispatch path
  (L1527–1540) raises `EXECUTOR_PROJECT_BUSY` (`ErrorCode.UNAVAILABLE`) without
  inserting a running Attempt; `persistent_task_core.py` `drain_outbox_once`
  releases/rejects and retries; Task Core `task.running` is gated on an
  authoritative `attempt.running` observation.
- Trigger path: accepted Task whose dispatch sees the same project busy →
  outbox retry (35 deliveries observed in the Post-Alpha run) → Attempt unbound.
- Affected state: Task remains `accepted` (not running) at the backend; the
  user-visible "已开始处理"/running wording is a presentation-layer risk.
- Existing tests: `test_p3_authenticated_composition.py` admission/retry paths;
  `test_persistent_task_core.py` outbox/claim/dispatch tests.
- Missing tests: an explicit display-layer test that accepted/queued is never
  rendered as running.
- Verdict: **backend state machine is correct; the residual risk is display
  wording, not authoritative state.** Risk: Medium. Owner: Integrated Web
  presentation + Task Core admission wording.

### B3 — Semantic routing (Chinese adjustment/status fixed "把/将" grammar)

- Source: `voice_task_bridge.py` `_UNIFIED_UPDATE` (L397–403) requires
  `(?:请)?(?:把|将)` plus a fixed verb list; `_UNIFIED_STATUS` (L326–336) requires
  fixed topic prefixes; `_UNIFIED_ADJUSTMENT_STATUS` (L337–347) rejects prefixed
  forms. Confirmed by P3 and P2 and re-read by the main session.
- Trigger path: a valid Chinese adjustment without "把/将", or a
  conversationally-prefixed status question, fails the `fullmatch` and falls
  through to DIALOGUE (no `task.adjust` side effect) — a false-negative
  (fail-safe), and a documented closed-form vs feature-complete gap.
- Affected state: no Task mutation; the request is mis-routed to dialogue.
- Existing tests: `test_voice_task_bridge.py` (16 lines added at `ca9a9d9a` for
  inner-trip classification, not grammar generalization).
- Missing tests: a no-"把/将" adjustment and prefixed status regression.
- Verdict: **still a blocker for feature-complete semantic routing.** Risk: High.
  Owner: Voice–Task Bridge.

### B4 — Task-truth isolation (foreground dialogue inferring applied/completed/result)

- Source: five-layer isolation verified by P2: (1)
  `select_formal_context` only yields `cr_committed_user`+`cr_presented_assistant`;
  (2) DIALOGUE route rejects Task authority
  (`voice_task_bridge.py` L1154–1169); (3)
  `_bounded_untrusted_result_context` marks `authority:none`/`tool_authority:False`
  and injects only for `BACKGROUND_QUERY`; (4) `jiuwenswarm_round_harness.py`
  `commit_round` forces `allow_tools=False` on `live_voice.task_result`
  (L548–552); (5) `stream_event_rail.py` hard-denies
  `FORMAL_TOOL_EXECUTION_FORBIDDEN` for no-tool sessions. Task state/outcome/
  result is owned only by Store/Core (`task_store.py` L3824–3832 is the single
  terminal flip point).
- Trigger path: DIALOGUE `allow_tools=True` ordinary Agent tools are not
  enumerated/denied by live_voice, but there are no `task.*` tools, no
  `project_dir`, and the background worktree is isolated.
- Affected state: no Task-state mutation; residual risk is voice/presentation
  hallucination (the Post-Alpha foreground Agent "re-read 7 order files and
  claimed the adjustment was applied" is this presentation-hallucination class,
  not a Task-truth write).
- Existing tests: `test_task_progress_return.py`, `test_product_composition_registry.py`
  result-context tests, `tests/unit_tests/agentserver/test_formal_live_voice_adapter.py`
  tool-removal tests.
- Missing tests: an end-to-end negative test that a DIALOGUE `chat.final`
  asserting applied/completed/result cannot enter Task/history truth.
- Verdict: **downgraded from blocker to LOW residual risk** — isolation is
  source-backed; the gap is a missing end-to-end negative oracle plus
  presentation wording, not a Task-truth mutation path. Risk: Low. Owner: Agent
  Bridge (add the negative oracle).

### B5 — Result-context capacity rejecting a legal TaskResult

- Source: `product_composition_registry.py` `_bounded_untrusted_result_context`
  and its caller (registry ~L4222) uses `len(context.entries) >= 8` to reject a
  legal, available TaskResult when the dialogue snapshot already occupies the
  selected capacity (Post-Alpha observation: 8 entries → "当前任务结果不可用").
- Trigger path: completed Task whose result-context injection is refused because
  the bounded dialogue context is full.
- Affected state: a truthful TaskResult becomes unavailable to the user; no
  fabricated success is produced (fail-closed), but the legitimate result is
  lost to presentation.
- Existing tests: `test_product_composition_registry.py`
  `test_unified_task_result_context_is_bounded_and_rejects_unsafe_artifacts`
  covers safety + 32KB bound, **not** the capacity-full rejection of a legal
  result.
- Missing tests: a capacity-full-but-legal-result test.
- Verdict: **still a blocker.** Risk: High. Owner: Agent Bridge / registry
  result-context.

### B6 — Recovery diagnostics ("正在恢复" lacks seam correlation)

- Source: correlation primitives are complete
  (`observability.py` `TraceBinding` + segment matrix + `by_correlation`, tested);
  formal frontend recovery does carry correlation (P2 activation journal, task
  intent checkpoint, P3 progress, P1 media all carry session/correlation/
  activation ids). The gaps: backend `product_observability_adapter.py` is
  package-only and **not composed** (no runtime caller); the user-visible
  `liveVoice.status.recovering` → "正在恢复" is a single ambiguous label
  (`ChatPanel/index.tsx` L1307–1314 carries only `p1_status`/`text`); the legacy
  streaming-final-timeout `recover` path has no correlation; `conversation_runtime.py`
  /`conversation_runtime_loop.py` carry no correlation (only
  `agent_conversation_runtime.py` does).
- Trigger path: repeated P2/barge and Speech transport cleanup errors coincide
  with visible recovery states; the operator cannot attribute the failure to the
  activation/generation/ACK/TTS seam.
- Affected state: diagnosis only (no mutation); recovery retry vs terminal
  failure is not stably distinguishable.
- Existing tests: `test_observability.py` (correlation/identity bindings),
  `test_product_observability_adapter.py`.
- Missing tests: an end-to-end recovery correlation test across the four seams.
- Verdict: **still a blocker for stable recovery diagnostics.** Risk: Medium.
  Owner: Observability + Conversation Runtime (compose the adapter, enrich the
  recovering label).

## 8. New findings

1. `_base_registrations` in `product_composition_registry.py` (L1574–1596)
   registers `P1_SPEECH_MEDIA` and `P3_CONTROL` as **always-unavailable**
   (`_media_unavailable`, `_control_unavailable`) in the backend composition;
   those segments are only formally composed at the gateway/frontend. This is a
   seam-owner clarification, not a defect.
2. `realtime_media.py` is not composed; `browserAudioDeviceSelection.ts` is not
   wired into the formal adapter; `interaction_engine.py` is a contract fake;
   `fakeP1Vertical.ts` and `conversationRuntimeReplica.ts` are dead test/support
   modules in the production tree (reinforces the branch-retirement audit).
3. The Post-Alpha `deepseek-v4-flash` model label (dirty run) is a machine-private
   runtime fact; the audited source has no model hardcode in product code (the
   "Three-day itinerary" hardcode was extracted to
   `demo_fixture_contract.DEMO_ITINERARY_TASK_NAME` at `ca9a9d9a`).

## 9. Hardcode ledger

| Hardcode | Owner | Retirement condition |
|---|---|---|
| `_UNIFIED_TRIP_CREATE` "N 天行程/旅行计划" + `_UNIFIED_ITINERARY_FILE_CREATE` `itinerary.md` (voice_task_bridge.py) | Voice–Task Bridge | Generalize task input/confirmation; retire with Demo fixture |
| `DEMO_ITINERARY_TASK_NAME` (`demo_fixture_contract.py`) | Demo fixture contract | Retire with explicit Demo profile after clean Journey |
| Demo itinerary/checkpoint/bypass (`scripts/live_voice/start_hands_free_demo.ps1`) | Demo launcher | Parameterize + move to demo/test support or delete |
| `.env.production` three Live Voice flags | Integrated Web | Explicit Demo profile replacing default-on production flags |
| `PRODUCT_DEMO_POLICY_BYPASS_ENV` (`demo_policy_bypass_enabled`) | Authority composition | Remove after generalized confirmation/policy |
| Protocol/safety constants (schema versions, `MAX_SAFE_INTEGER`, identity patterns, error vocabularies in `observability.py`, `product_composition_contract.py`) | respective owners | Retain (protocol/safety) |

## 10. Duplicate / consolidation ledger

| Duplication | Locations | Semantic match | Consolidation timing |
|---|---|---|---|
| Registry generation-index traversal | `_p2_response_generation_indices` / `_closed_p2_generation_indices` (`product_composition_registry.py` L830/L964) | yes, differing state predicate | During the registry defect-repair batch only |
| Strict record validation / exact-object validation / P2 activation binding equality | `formal/liveVoiceContractV2.ts`, `liveVoiceRouteTelemetry.ts`, `liveVoiceObservability.ts`, `productP2ActivationJournal.ts`, `productP3ProgressGenerationJournal.ts`, `productWebActivation.ts` | yes (helpers), keep error wording | With the next formal Web cleanup |
| Parallel Task models | `task_core.py` (in-memory) vs `persistent_task_core.py`+`task_store.py` (SQLite) | overlapping, not identical | Migrate bridge/product callers, then retire old model (before multi-Task) |
| Parallel executors | `DirectProjectCodeExecutorAdapter` vs `ProjectCodeExecutorAdapter` (compatibility) | distinct | Retire compatibility adapter after Direct terminal/recovery acceptance + caller audit |
| Operation-name allowlists | `p3_authenticated_composition.py`, `product_p3_text_adapter.py`, `product_composition_registry.py` | intentionally different | Derive from a canonical capability catalog (no premature merge) |
| Cross-language v2 contract parity | backend `live_voice_contract_v2` vs frontend `liveVoiceContractV2.ts` | trust boundary | Keep until a generated validator replaces manual parity |

Authority handlers with different target binding/idempotency/side-effect
semantics stay explicit (per the duplication audit, no broad generic framework).

## 11. Cross-module dependencies and authority seams

- Composition authority: `product_composition_contract.py` `ProductRouteTruth`/
  `ProductSegment`/`ProductRouteFact` (Gate-0) → `product_composition_root.py`
  `ProductCompositionRoot` (default-off, authority-first activation, retained
  LIFO cleanup) → `product_composition_registry.py`
  `create_product_composition_registry_from_environment` (master env gate, returns
  `None` when off).
- State authority: Task state/outcome/result owned by `SqliteTaskStore` +
  `PersistentTaskCore`; the single terminal flip is `task_store.py` L3824–3832.
- Cancel/fence: `executor_port.py` + `_DirectExecutorJournal` (attempt),
  `product_composition_contract.py`/registry (route), observability cancel scopes.
- Recovery/durability: executor lease journal (`project_code_executor.py`),
  `unified_committed_input.py` recovery_json, P2/P3 frontend journals
  (`productP2ActivationJournal.ts`, `formalTaskIntentRoute.ts` recovery
  checkpoint), `persistent_task_core.py` reconcile.
- Identity: `formal_task_models.py` (Task/Attempt/Event/Command), observability
  `TraceBinding` (correlation/interaction/turn/response/round/task/attempt).
- Remaining seam gaps: media segment (gateway vs backend composition), Interaction
  Intelligence ownership split, observability adapter non-composition, legacy
  `useLiveVoiceDemo` lane still constructed.

## 12. Removable / retirement ledger

| Item | Disposition | Retirement gate | Safe now? |
|---|---|---|---|
| Legacy `useLiveVoiceDemo`/`liveVoiceCore`/streaming-speech/Task client-adapter-bridge-monitor lane | REPLACE-THEN-REMOVE | formal route default + clean Journey + flag-off regressions | no |
| Old `task_core.py` model | REPLACE-THEN-REMOVE | migrate bridge to formal model, pass restart/result/cancel | no |
| `ProjectCodeExecutorAdapter` (compatibility) | REPLACE-THEN-REMOVE | Direct terminal/recovery acceptance + caller audit | no |
| `.env.production` default-on flags | REPLACE (explicit Demo profile) | Demo profile shipped | no |
| `realtime_media.py`, `fakeP1Vertical.ts`, `conversationRuntimeReplica.ts` | RE-HOME or REMOVE | move test/support or delete after oracle migration | re-home first |
| `alpha_benchmark.py`, `alpha_privacy_conformance.py`, `observability_fault_harness.py` | RE-HOME | move reusable oracles to test/validation support | re-home first |
| S7/S8 stage scripts + `test_s7_*`/`test_s8_*` | REMOVE after regression transplant | migrate applicable oracles to capability tests | after transplant |
| W2 dotenv flags, legacy ticket-in-path media routing, `live_voice_snapshot.ps1` | REMOVE-CANDIDATE | final caller/flag search + affected tests | with mechanical cleanup |

## 13. Tests and missing-oracle map

- Backend: 55 live-voice source modules vs 42 test modules. Modules with **no
  direct backend test module**: `browser_gateway_media_transport`,
  `dedicated_media_registration`, `dedicated_media_route`, `demo_fixture_contract`,
  `fake_verticals`, `formal_history_writer`, `formal_task_models`,
  `jiuwenswarm_agent_adapter`, `jiuwenswarm_round_harness`, `p3_model_resolution`,
  `presentation_ledger`, `product_streaming_synthesis`, `speech_rpc`,
  `streaming_speech_route`, `streaming_synthesis_route`, `task_store`,
  `voice_task_policy`. Several are covered indirectly (`task_store` via
  `test_persistent_task_core.py`, `formal_task_models` via task-core tests) or by
  frontend tests (gateway media/transport); the rest are missing oracles.
- Missing oracles (highest value): (a) end-to-end DIALOGUE cannot assert Task
  truth (B4 closure); (b) result-context capacity-full legal-result rejection
  (B5); (c) recovery correlation across activation/generation/ACK/TTS (B6);
  (d) no-"把/将" adjustment + prefixed status routing (B3); (e) display-layer
  accepted/queued ≠ running (B2).
- Still-old-runner oracles: S7/S8 stage-named scripts/tests remain and must be
  migrated before deletion.

## 14. Focused tests and results

No focused tests were run. Static source + test-source + the Post-Alpha runtime
record were sufficient to adjudicate all 15 domains and 6 blockers; none of the
required-focus conditions (ambiguous static call chain, flag-on/off not
determinable statically, multiple state-transition owners, old-test/current-code
conflict, blocker-reproducibility only via dynamics, forbidden side effect
needing dynamic proof) was met for a read-only audit. The four subagent-suggested
commands (`test_unified_update_binds_current_nonterminal…`,
`test_projection_preserves_source_truth…`, `test_one_journey_keeps_correlation…`,
`test_formal_task_result_policy_removes_and_hard_denies_tools`) are recorded as
candidate follow-up evidence, not run.

Not run: full backend suite; full frontend suite; any physical microphone/TTS/
Agent/Executor journey. Cannot run here: a clean physical acceptance (requires
microphone, Provider, Agent, isolated disposable project, and an immutable
candidate — machine-private environment).

## 15. Unresolved issues and evidence limits

1. B1/B2 clean-source status depends on a clean physical re-verification; the
   Post-Alpha dirty-source observations cannot be confirmed or denied statically.
2. The Post-Alpha dirty working-tree candidate changes are not in Git, so the
   exact runtime source cannot be reconstructed for a diff-level root cause.
3. Interaction Intelligence ownership split (Speech vs `voice_task_bridge` vs
   registry vs `interaction_engine.py` contract) is a boundary question needing a
   main-session/owner decision, not a code fix.
4. Realtime Media's formal composition owner (gateway vs backend vs frontend)
   remains to be pinned before granting any formal credit.
5. No immutable PASS exists for the hands-free journey; all historical PASS
   credit stays bound to its exact source.

## 16. Final conclusion

All 15 capability domains have code and test evidence. Fourteen are PARTIAL and
one (Production operations) is NOT STARTED; Executor & Durability is re-scored
from BLOCKED to PARTIAL because the terminalization/admission truth path is
statically closed and unit-tested on this source, with the D1/D2/capability gaps
belonging to feature-complete scope and the clean physical re-verification left
open. Of the six known blockers: B3 and B5 remain High blockers; B6 remains a
Medium blocker; B4 is downgraded to a Low residual (isolation is source-backed,
missing only an end-to-end negative oracle); B1 and B2 are partially closed on
this clean source with clean re-verification and display-wording work remaining.
This audit is documentation, not product progress: it does not repair defects,
does not upgrade product readiness, and does not trigger `develop` integration.

## 17. Recommended fix order

1. Compose the observability adapter + enrich the "正在恢复" correlation (B6,
   Medium) and add the recovery-seam test.
2. Repair `_bounded_untrusted_result_context` capacity-full rejection of a legal
   TaskResult and add the missing test (B5, High).
3. Generalize `_UNIFIED_UPDATE`/`_UNIFIED_STATUS` beyond "把/将" fixed grammar and
   prefixed status forms, add regressions (B3, High).
4. Add the end-to-end DIALOGUE-cannot-assert-Task-truth negative oracle and fix
   the accepted/queued ≠ running display wording (B4/B2).
5. Clean physical acceptance on one immutable candidate to close the B1/B2
   re-verification and confirm Executor terminal truth end-to-end.
6. Then execute the branch-retirement/duplication/code-organization batches and
   the D1/D2/capability-driven Executor work toward feature-complete.
