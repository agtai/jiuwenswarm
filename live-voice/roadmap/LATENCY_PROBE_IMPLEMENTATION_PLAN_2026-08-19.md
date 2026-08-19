# Live Voice Minimal Latency Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Plan status:** READY FOR REVIEW — no implementation or measurement credit.
>
> **Planning code baseline:** `62605dd103dafa5a988a9f63f42b4cad45a2d902`.
> Revalidate Git and current owners before execution; Git remains the code fact.

**Goal:** Add a default-off experimental probe that records the real Integrated Web voice path, produces a reproducible current-source baseline, and compares one optimization at a time without changing product authority or behavior.

**Architecture:** The Browser owns the only additive end-to-end clock and sends one best-effort batch after a round terminal. Gateway and Agent Server write separate same-process JSONL drill-down batches. A small shared Python contract validates the closed records and immutable `run.json`; a separate offline reducer produces JSON, CSV, Markdown, and baseline/candidate comparisons. Existing owners emit marks locally, and the four-field diagnostic context is removed before business validation.

**Tech Stack:** Python 3.11 dataclasses/stdlib JSON, pytest/pytest-asyncio, TypeScript, React, WebAudio, Vite/esbuild, Node test runner, existing JiuwenSwarm WebSocket RPC and dedicated-media routes.

**Spec:** [`live-voice/roadmap/LATENCY_PROBE_SPEC_2026-08-19.md`](LATENCY_PROBE_SPEC_2026-08-19.md)

## Global Constraints

- This packet implements the minimal spec only. Do not import or reproduce the `FULL_` graph, catalog, span, dynamic critical-path, or hot-path designs.
- Before Task 1, re-run `git status --short --branch`, `git rev-parse HEAD`, and the selected README/STATUS route. Record any owner drift against this planning baseline before editing code.
- Keep the probe default-off. Feature-off creates no recorder, callback, batch request, output directory, or output file.
- Probe failure is diagnostic-only. It must not reject, retry, acknowledge, reroute, or change Speech, Agent, Tool, Task, media, presentation, history, cancellation, or next-turn operations.
- Use `time.monotonic_ns() / 1_000_000` in Python and `performance.now()` in the Browser. Never subtract clocks from different `clock_domain_id` values.
- Never record audio, text, prompt, response, Tool/Task content, credentials, URLs, filesystem paths, exception text, tracebacks, or arbitrary metadata.
- Keep one writer per process file: Gateway writes `browser.jsonl` and `gateway.jsonl`; Agent Server writes `agent.jsonl`. One batch is one canonical JSONL line.
- Preserve existing observability. This probe is a separate development measurement seam, not a replacement exporter.
- Follow root `TESTING.md` Tier-3 protocol evidence for the new shared contract and RPC seam: positive journeys, applicable negative boundaries, zero forbidden side effects, privacy sentinels, fault injection, and independent review.
- Do not update `STATUS.md` to claim a baseline until the real warm and cold runs satisfy the sample requirements. Do not begin an optimization in this packet.

## Fixed names and configuration

Use these names consistently:

```text
Backend enable:      JIUWENSWARM_LIVE_VOICE_LATENCY_PROBE_ENABLED
Run config:          JIUWENSWARM_LIVE_VOICE_LATENCY_PROBE_RUN_CONFIG
Private output root: JIUWENSWARM_LIVE_VOICE_LATENCY_PROBE_OUTPUT_ROOT
Frontend enable:     VITE_FEATURE_LIVE_VOICE_LATENCY_PROBE
Browser query:       lv_latency_run, lv_latency_profile, lv_latency_case
Browser batch RPC:   live_voice.latency_probe.batch
```

The Browser obtains `run_id`, `profile_id`, and `input_case_id` from the three query parameters only when the frontend flag is true. It allocates `round_index` in `sessionStorage`, keyed by those three values. A page/session restart starts a new run rather than guessing the prior index. Gateway and Agent Server validate the resulting context against the immutable `run.json`.

The first implementation creates these modules:

```text
jiuwenswarm/server/live_voice/latency_probe.py
jiuwenswarm/server/live_voice/latency_probe_report.py
jiuwenswarm/gateway/live_voice/latency_probe_registration.py
jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/latencyProbe.ts
```

The closed Python public types are `LatencyProbeContext`, `LatencyMark`,
`LatencyBatch`, `LatencyRunConfig`, `LatencyProbeRecorder`,
`LatencyProbeBatchWriter`, and `LatencyProbeRuntime`. The public factories are
`load_latency_run_config(path: Path) -> LatencyRunConfig`,
`create_latency_probe_runtime_from_environment(component: str) ->
LatencyProbeRuntime | None`, and
`try_parse_latency_probe_context(value: object, run: LatencyRunConfig) ->
LatencyProbeContext | None`.

`LatencyProbeRecorder.mark(...)` accepts only a fixed/core or run-declared experiment point plus closed identity fields. `finish(...)` freezes one batch exactly once. The clock and ID factories are injectable in tests.

---

## Task 1: Implement the closed Python contract and recorder

**Files:**

- Create: `jiuwenswarm/server/live_voice/latency_probe.py`
- Create: `tests/unit_tests/live_voice/test_latency_probe.py`

- [ ] **Step 1: Write failing contract/config tests**

Add tests that construct a valid `run.json` and assert exact parsing of all five profiles, declared input cases, core points, declared `experiment.<id>.<fact>` points, and the four-field `LatencyProbeContext`. Reject unknown keys, overlong strings, invalid numbers, undeclared profiles/cases/experiment points, private-field names, and mismatched run IDs.

```python
def test_context_is_closed_and_bound_to_run(run_config):
    context = try_parse_latency_probe_context(
        {
            "schema_version": "live-voice.latency-context.v0",
            "run_id": run_config.run_id,
            "profile_id": "dialogue_no_tool",
            "input_case_id": "short-greeting-v1",
            "round_index": 0,
        },
        run_config,
    )
    assert context is not None
    assert context.round_index == 0
    assert try_parse_latency_probe_context({**context.to_dict(), "text": "PRIVATE"}, run_config) is None
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `uv run pytest -q tests/unit_tests/live_voice/test_latency_probe.py`

Expected: import failure because `latency_probe.py` does not exist.

- [ ] **Step 3: Implement the immutable run config and closed records**

Use frozen, slotted dataclasses and explicit exact-key validators. Keep the five profile IDs, component IDs, phases, outcomes, reason codes, core points, maximum 64 marks, and schema versions as closed constants. `LatencyMark.to_dict()` and `LatencyBatch.to_dict()` must emit canonical field order and no optional arbitrary mapping.

- [ ] **Step 4: Add failing recorder/writer/factory tests**

Cover monotonic mark indices, duplicate point rejection, capacity behavior, finish-once behavior, canonical batch bytes, identical batch retry, conflicting `batch_id`, one-line JSONL append, injected write failure, and feature-off zero allocation/files. Patch all three environment variables in the tests; never use the developer's real environment.

```python
recorder = LatencyProbeRecorder(
    context=context,
    component="gateway",
    phase="gateway_stt",
    source_instance_id_factory=lambda: "source-1",
    clock_domain_id="gateway-process-1",
    monotonic_ms=lambda: 10.0,
)
recorder.mark("gateway.stt_request_started", correlation_id="corr", interaction_id="ix")
batch = recorder.finish("completed")
assert [mark.mark_index for mark in batch.marks] == [0]
```

- [ ] **Step 5: Implement recorder, batch writer, and environment factory**

The runtime loads and validates `run.json` before creating writers. The writer uses a process-local lock and appends one canonical UTF-8 JSON object plus `\n` per completed batch. It retains `batch_id -> sha256(canonical_bytes)` only up to a bounded limit, treats an identical retry as idempotent, and returns a closed diagnostic result instead of raising into product code. No directory is created on the feature-off path.

- [ ] **Step 6: Run focused tests and commit**

Run: `uv run pytest -q tests/unit_tests/live_voice/test_latency_probe.py`

Expected: PASS.

```bash
git add jiuwenswarm/server/live_voice/latency_probe.py tests/unit_tests/live_voice/test_latency_probe.py
git commit -m "feat(live-voice): add minimal latency probe contract"
```

## Task 2: Implement the fixed reducer, reports, and comparison CLI

**Files:**

- Create: `jiuwenswarm/server/live_voice/latency_probe_report.py`
- Create: `tests/unit_tests/live_voice/test_latency_probe_report.py`

- [ ] **Step 1: Write failing fixed-segment tests**

Build deterministic batches for every segment in spec sections 7 and 8. Assert that same-clock pairs produce the expected duration; missing, duplicate, identity-mismatched, and cross-clock pairs produce `unknown`, never zero. Assert nearest-rank p50/p95 and separate cold/warm populations.

```python
report = reduce_latency_run(run_config, batches)
response = report.profile("dialogue_no_tool").segment("response_total")
assert response.successful_samples == 1
assert response.p50_ms == 850.0
assert response.unknown == 0
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `uv run pytest -q tests/unit_tests/live_voice/test_latency_probe_report.py`

Expected: import failure because the report module does not exist.

- [ ] **Step 3: Implement fixed definitions and reduction**

Define one immutable `SegmentDefinition` tuple containing `segment_id`,
start/end point, component, phase tags, primary capability, and applicable
profiles. Implement the exact public functions `read_latency_batches(run_dir:
Path) -> tuple[LatencyBatch, ...]`, `reduce_latency_run(run: LatencyRunConfig,
batches: Iterable[LatencyBatch]) -> LatencyRunReport`,
`write_latency_report(report: LatencyRunReport, output_dir: Path) -> None`, and
`compare_latency_reports(baseline: LatencyRunReport, candidate:
LatencyRunReport) -> LatencyComparison`.

Write deterministic `report.json`, `report.csv`, and `report.md`. The Markdown report has one summary table and one textual waterfall per profile. Do not add plotting dependencies; CSV is the graph input.

- [ ] **Step 4: Add failing comparison and CLI tests**

Cover compatible/incompatible configs, `improved`, `shifted`, `regressed`, and `inconclusive`; count/rate guardrails; insufficient samples; dirty-source rejection for baselines; and a subprocess smoke test for:

```bash
uv run python -m jiuwenswarm.server.live_voice.latency_probe_report validate-run --run-json /tmp/live-voice-latency/run.json
uv run python -m jiuwenswarm.server.live_voice.latency_probe_report report --run-dir /tmp/live-voice-latency/run
uv run python -m jiuwenswarm.server.live_voice.latency_probe_report compare --baseline /tmp/live-voice-latency/baseline/report.json --candidate /tmp/live-voice-latency/candidate/report.json
```

- [ ] **Step 5: Implement the three CLI subcommands and re-run tests**

Run: `uv run pytest -q tests/unit_tests/live_voice/test_latency_probe.py tests/unit_tests/live_voice/test_latency_probe_report.py`

Expected: PASS with exact JSON/CSV/Markdown golden assertions.

- [ ] **Step 6: Commit**

```bash
git add jiuwenswarm/server/live_voice/latency_probe_report.py tests/unit_tests/live_voice/test_latency_probe_report.py
git commit -m "feat(live-voice): add latency baseline reducer"
```

## Task 3: Add the isolated Gateway Browser-batch seam

**Files:**

- Create: `jiuwenswarm/gateway/live_voice/latency_probe_registration.py`
- Create: `tests/unit_tests/gateway/test_latency_probe_registration.py`
- Modify: `jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py`
- Modify: `tests/unit_tests/test_app_web_live_voice_privacy.py`

- [ ] **Step 1: Write failing handler tests**

Specify `LATENCY_PROBE_BATCH_METHOD = "live_voice.latency_probe.batch"` and
`register_latency_probe_rpc_handler(channel: object, runtime:
LatencyProbeRuntime | None) -> None`. The request envelope is closed to
`{"session_id": <dispatcher-owned session>, "batch": <LatencyBatch>}`;
`session_id` is used only for request authorization and is not written into the
probe batch.

Test that feature-off registers no method. With the runtime enabled, accept one closed `browser_round` batch only for the dispatcher-owned session/run/profile/case, append exactly one `browser.jsonl` line, make an identical retry idempotent, and reject conflicting bytes, wrong session/run/round, sequence gaps, oversized batches, and private sentinels.

- [ ] **Step 2: Assert zero product side effects**

Inject spies for media, Speech, Agent, Tool, Task, presentation, history, ACK, and next-turn owners. For every negative case and an injected writer failure, assert all spy counts remain zero and the voice/product registry is unchanged.

- [ ] **Step 3: Run the tests and confirm RED**

Run: `uv run pytest -q tests/unit_tests/gateway/test_latency_probe_registration.py tests/unit_tests/test_app_web_live_voice_privacy.py`

Expected: missing registration module/handler failures.

- [ ] **Step 4: Implement the handler and bootstrap wiring**

Create the Gateway runtime once in `_register_web_handlers`, then register the diagnostic method only when it is non-null. The handler validates before writing, returns only `{status, batch_id, reason_code}`, catches ordinary validation/I/O failures, and never invokes an existing product owner. Keep process-control exceptions uncaught.

- [ ] **Step 5: Re-run tests and commit**

Run: `uv run pytest -q tests/unit_tests/gateway/test_latency_probe_registration.py tests/unit_tests/test_app_web_live_voice_privacy.py tests/unit_tests/gateway/test_dedicated_media_registration.py`

Expected: PASS.

```bash
git add jiuwenswarm/gateway/live_voice/latency_probe_registration.py jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py tests/unit_tests/gateway/test_latency_probe_registration.py tests/unit_tests/test_app_web_live_voice_privacy.py
git commit -m "feat(live-voice): accept browser latency batches"
```

## Task 4: Implement the Browser recorder and run selector

**Files:**

- Create: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/latencyProbe.ts`
- Create: `jiuwenswarm/channels/web/frontend/tests/liveVoiceLatencyProbe.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/src/featureFlags.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/vite-env.d.ts`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

- [ ] **Step 1: Write failing parser and recorder tests**

Test default-off returns `null` without reading storage or installing callbacks. Test closed parsing of the three query fields, all five profiles, bounded `sessionStorage` allocation, monotonic `mark_index`, capacity, duplicate points, finish-once, exact identity enrichment, and content/private-sentinel rejection.

The TypeScript surface is:

```ts
export type LatencyProbeContext = Readonly<{
  schema_version: 'live-voice.latency-context.v0';
  run_id: string;
  profile_id: LatencyProfileId;
  input_case_id: string;
  round_index: number;
}>;

export interface BrowserLatencyRound {
  readonly context: LatencyProbeContext;
  mark(point: BrowserLatencyPoint, identity: LatencyIdentityPatch, observation?: LatencyObservation): void;
  finish(outcome: LatencyTerminalOutcome): Readonly<LatencyBatch> | null;
}

export interface BrowserLatencyProbe {
  beginRound(identity: LatencyIdentityPatch): BrowserLatencyRound;
  exportBatch(sessionId: string, batch: Readonly<LatencyBatch>): Promise<void>;
}
```

- [ ] **Step 2: Run the new frontend script and confirm RED**

Add `test:live-voice-latency-probe` to compile only `latencyProbe.ts`, bundle it to `node_modules/.cache/live-voice-latency-probe/latencyProbe.mjs`, and run the new Node test.

Run: `npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-latency-probe`

Expected: compile/import failure until the module is implemented.

- [ ] **Step 3: Implement the closed Browser recorder**

Inject `performance.now`, random ID, `Location`, and `Storage` adapters.
`exportBatch` calls the existing request transport once with the closed
`session_id`/`batch` envelope for `live_voice.latency_probe.batch`; it catches
rejection and never retries a product request. Retain no transcript or product
payload. Do not use `localStorage`.

- [ ] **Step 4: Re-run tests and commit**

Run: `npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-latency-probe`

Expected: PASS.

```bash
git add jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/latencyProbe.ts jiuwenswarm/channels/web/frontend/tests/liveVoiceLatencyProbe.test.mjs jiuwenswarm/channels/web/frontend/src/featureFlags.ts jiuwenswarm/channels/web/frontend/src/vite-env.d.ts jiuwenswarm/channels/web/frontend/package.json
git commit -m "feat(live-voice): add browser latency recorder"
```

## Task 5: Instrument the Browser-owned end-to-end timeline

**Files:**

- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/unifiedCommittedInputOwner.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`
- Modify: `jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceBrowserAudioIOAdapter.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/tests/unifiedCommittedInputOwner.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceGatewayBatchSpeech.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs`

- [ ] **Step 1: Write failing round-lifecycle tests**

Test a deterministic no-Tool round from initial capture through B0–B10. A capture owns round N. When EOT is accepted, round N becomes the response round. Concurrent capture preparation allocates round N+1 for the next input while recording `successor_capture_requested/ready` on N. The TTS request retains N; the successor media activation retains N+1.

Define B10 precisely as the first Browser instant when both conditions are true: the current response's B9 ACK has returned and its prepared successor capture is ready. This preserves the current capture/playout overlap while making `round_total` a terminal lifecycle duration. Export round N once at B10; export a failed/cancelled round at its stable terminal.

- [ ] **Step 2: Add failing audio timing tests**

Extend the audio observer with a diagnostic-only first-frame timing event. At the first accepted schedule:

```ts
const timestamp = context.getOutputTimestamp?.();
const estimatedStartMs = timestamp
  ? timestamp.performanceTime + (nextStartTime - timestamp.contextTime) * 1000
  : nowMs + Math.max(0, nextStartTime - context.currentTime) * 1000;
const uncertaintyMs = Math.max(
  128 / context.sampleRate * 1000,
  Number(context.outputLatency ?? context.baseLatency ?? 0) * 1000,
);
```

Assert B6 uses the scheduling call's `performance.now()`, B7 uses `estimatedStartMs`, and only B7 has non-null uncertainty. Also assert underrun/rebuffer marks and no behavior change when no diagnostic observer exists.

- [ ] **Step 3: Run the focused Browser tests and confirm RED**

Run:

```bash
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-latency-probe
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-browser-audio-io
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-gateway-batch-speech
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-integrated-web
```

Expected: new lifecycle/timing assertions fail.

- [ ] **Step 4: Wire owner-local points and context**

Instrument the exact current owners:

- `ProductP1VoiceRouteOwner`: capture request/device start, media attach, first frame send/ACK, EOT, capture stop, last send/ACK, uplink close, STT final, TTS request, downlink attach/first frame, playout schedule/estimate/completion, media receipt ACK, successor request/ready, B10, failure/cancel/fallback;
- `ProductUnifiedCommittedInputOwner`: accept an optional already-validated context argument and include `latency_probe_context` only when present;
- `GatewayBatchSpeechClient`: carry the response-round context on synthesis calls without changing feature-off request shapes; STT obtains its input-round context from the already-bound media activation;
- `LiveVoiceIntegratedRoutePanel`: create the probe from flag/query, mark B2 before unified submit and B3 on the bound foreground PresentationUnit, enrich turn/response/task identity, and ignore excluded background terminal notifications;
- `BrowserAudioIOAdapter`: publish timing facts through the optional diagnostic observer only.

Do not export from every mark. `ProductP1VoiceRouteOwner` exports one frozen Browser batch through the injected probe at terminal, and an export failure is swallowed after recording `EXPORT_FAILED` when capacity permits.

- [ ] **Step 5: Add negative/fault/privacy cases**

Cover stale activation/response generations, duplicate EOT/presentation, fallback, cancel, audio failure, batch RPC failure, component unmount, and private sentinels in recognized/Agent/Tool/Task/error content. Assert identical product request counts and authoritative state with probe enabled versus disabled, except for the single diagnostic batch request.

- [ ] **Step 6: Re-run tests and commit**

Run the four commands from Step 3 plus
`npm --prefix jiuwenswarm/channels/web/frontend run build`.

Expected: PASS.

```bash
git add jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/unifiedCommittedInputOwner.ts jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs jiuwenswarm/channels/web/frontend/tests/liveVoiceBrowserAudioIOAdapter.test.mjs jiuwenswarm/channels/web/frontend/tests/unifiedCommittedInputOwner.test.mjs jiuwenswarm/channels/web/frontend/tests/liveVoiceGatewayBatchSpeech.test.mjs jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs
git commit -m "feat(live-voice): measure browser voice rounds"
```

## Task 6: Instrument Gateway STT/VAD and TTS/downlink drill-downs

**Files:**

- Modify: `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py`
- Modify: `jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py`
- Modify: `jiuwenswarm/gateway/live_voice/streaming_speech_route.py`
- Modify: `jiuwenswarm/server/live_voice/openai_streaming_speech.py`
- Modify: `jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py`
- Modify: `jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py`
- Modify: `tests/unit_tests/gateway/test_dedicated_media_registration.py`
- Modify: `tests/unit_tests/gateway/test_streaming_speech_route.py`
- Modify: `tests/unit_tests/live_voice/test_openai_streaming_speech.py`
- Modify: `tests/unit_tests/gateway/test_streaming_synthesis_route.py`
- Modify: `tests/unit_tests/gateway/test_product_streaming_synthesis.py`

- [ ] **Step 1: Write failing STT mark tests**

Pass an optional `LatencyProbeContext`/sink into `StreamingRecognitionRouteOwner.begin`. Assert marks for request start, Provider transport open, session ready, Provider `speech_stopped`, EOT control send, and final available. Finalize one `gateway_stt` batch on completion/failure/fallback. The activation context is stored beside the existing exact activation record; stale generation cannot inherit it.

- [ ] **Step 2: Write failing TTS/downlink mark tests**

Pass the synthesis request context into `StreamingSynthesisRouteOwner.begin` and `start_product_streaming_synthesis`. Assert request received, Provider transport open, first Provider audio, ticket ready only after the first chunk, and first media frame sent. Finalize one `gateway_tts` batch. Test Provider failure before/after first audio, fence/cancel, and batch fallback.

- [ ] **Step 3: Run focused tests and confirm RED**

Run:

```bash
uv run pytest -q tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/gateway/test_streaming_speech_route.py tests/unit_tests/live_voice/test_openai_streaming_speech.py tests/unit_tests/gateway/test_streaming_synthesis_route.py tests/unit_tests/gateway/test_product_streaming_synthesis.py
```

Expected: context/sink parameters and mark assertions fail.

- [ ] **Step 4: Implement owner-local optional sinks**

Pass the Task 3 Gateway runtime from `_register_web_handlers` into the media
registry and STT/TTS owners. Create recorders only after closed context
validation. Emit marks immediately beside the authoritative state transition,
not in the caller after an await. Keep Provider callbacks content-free. Writer
errors are caught by the runtime and never affect route outcomes. Feature-off
must preserve exact request shapes and allocate no sink.

- [ ] **Step 5: Add identity, fault, and privacy tests**

Cover wrong run/profile/case, stale activation/response generation, selector/open timeout, Provider protocol error, writer failure, duplicate terminal, and recognizable sentinels in Provider text/audio/error objects. Assert zero extra commits, receipts, media tickets, ACKs, or retries.

- [ ] **Step 6: Re-run tests and commit**

Run the command from Step 3.

Expected: PASS.

```bash
git add jiuwenswarm/gateway/live_voice/dedicated_media_registration.py jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py jiuwenswarm/gateway/live_voice/streaming_speech_route.py jiuwenswarm/server/live_voice/openai_streaming_speech.py jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/gateway/test_streaming_speech_route.py tests/unit_tests/live_voice/test_openai_streaming_speech.py tests/unit_tests/gateway/test_streaming_synthesis_route.py tests/unit_tests/gateway/test_product_streaming_synthesis.py
git commit -m "feat(live-voice): measure gateway speech stages"
```

## Task 7: Instrument Agent Server foreground routing and execution

**Files:**

- Modify: `jiuwenswarm/server/agent_ws_server.py`
- Modify: `jiuwenswarm/server/live_voice/product_composition_registry.py`
- Modify: `jiuwenswarm/server/live_voice/agent_conversation_runtime.py`
- Modify: `jiuwenswarm/server/live_voice/voice_task_bridge.py`
- Modify: `tests/unit_tests/live_voice/test_product_composition_registry.py`
- Modify: `tests/unit_tests/live_voice/test_agent_conversation_runtime.py`
- Modify: `tests/unit_tests/live_voice/test_voice_task_bridge.py`
- Modify: `tests/unit_tests/live_voice/test_unified_committed_input.py`

- [ ] **Step 1: Write failing context-stripping and admission tests**

Create the Agent Server runtime once in
`_start_live_voice_product_composition`. In
`_handle_live_voice_product_request`, parse and remove
`latency_probe_context` before `handle_unified_submit` receives its closed
business `params`. Assert feature-off and malformed context leave the business
request unchanged and successful. With valid context, create one
`agent_foreground` recorder and mark `agent.commit_submit_received` before
registry dispatch.

- [ ] **Step 2: Write failing dialogue/Tool/Task fixture tests**

Use deterministic fixtures for:

- no-Tool dialogue: commit accepted → route resolved → Agent start → first `chat.delta` → `chat.final` → presentation produced/dispatched;
- one-Tool dialogue: first bound `chat.tool_call` → first subsequent bound
  `chat.tool_result`, plus the dialogue marks;
- foreground Task create/status/cancel: route resolved → authoritative Task command accepted → presentation produced/dispatched.

The adapter already carries typed `chat.tool_call` and `chat.tool_result` events; observe those event types without retaining tool names, arguments, IDs, or results. Replays must not create a second execution batch.

- [ ] **Step 3: Run focused tests and confirm RED**

Run:

```bash
uv run pytest -q tests/unit_tests/live_voice/test_product_composition_registry.py tests/unit_tests/live_voice/test_agent_conversation_runtime.py tests/unit_tests/live_voice/test_voice_task_bridge.py tests/unit_tests/live_voice/test_unified_committed_input.py
```

Expected: mark/context assertions fail.

- [ ] **Step 4: Thread one optional sink through existing owners**

Add keyword-only optional sink parameters; do not put probe fields into `TurnCommit`, `PresentationUnit`, Task records, journal fingerprints, history, or retained business results. Mark:

- commit accepted immediately after durable unified journal admission;
- route resolved after restoring the admitted semantic binding;
- Agent start at committed dispatch;
- first delta/final and first tool call/result in `_consume_agent_event`;
- Task command accepted only after the existing Task authority accepts it;
- presentation produced after `produce_unit`/`enqueue_unit` succeeds;
- presentation dispatched when the existing notification is published.

Finish and append the batch at presentation dispatch or a stable failure/cancel terminal.

- [ ] **Step 5: Add negative, replay, and privacy evidence**

Cover wrong run/round/session, malformed context, journal replay/conflict, Agent failure, Tool failure, Task denial, presentation failure, cancellation, writer failure, and private sentinels. Assert no new Agent/Tool/Task/history/presentation effects and no exception content in probe output.

- [ ] **Step 6: Re-run tests and commit**

Run the command from Step 3.

Expected: PASS.

```bash
git add jiuwenswarm/server/agent_ws_server.py jiuwenswarm/server/live_voice/product_composition_registry.py jiuwenswarm/server/live_voice/agent_conversation_runtime.py jiuwenswarm/server/live_voice/voice_task_bridge.py tests/unit_tests/live_voice/test_product_composition_registry.py tests/unit_tests/live_voice/test_agent_conversation_runtime.py tests/unit_tests/live_voice/test_voice_task_bridge.py tests/unit_tests/live_voice/test_unified_committed_input.py
git commit -m "feat(live-voice): measure foreground agent stages"
```

## Task 8: Close cumulative verification and the executable baseline loop

**Files:**

- Modify: `live-voice/runbooks/E2E_RUNBOOK.md`
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md`
- Modify after accepted real runs: `live-voice/STATUS.md`
- Create after accepted real runs: `live-voice/evidence/LATENCY_BASELINE_MINIMAL_PROBE_V0.md`

- [ ] **Step 1: Run cumulative automated verification**

```bash
uv run pytest -q tests/unit_tests/live_voice/test_latency_probe.py tests/unit_tests/live_voice/test_latency_probe_report.py tests/unit_tests/gateway/test_latency_probe_registration.py tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/gateway/test_streaming_speech_route.py tests/unit_tests/live_voice/test_openai_streaming_speech.py tests/unit_tests/gateway/test_streaming_synthesis_route.py tests/unit_tests/gateway/test_product_streaming_synthesis.py tests/unit_tests/live_voice/test_product_composition_registry.py tests/unit_tests/live_voice/test_agent_conversation_runtime.py tests/unit_tests/live_voice/test_voice_task_bridge.py tests/unit_tests/live_voice/test_unified_committed_input.py tests/unit_tests/test_app_web_live_voice_privacy.py
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-latency-probe
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-browser-audio-io
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-gateway-batch-speech
npm --prefix jiuwenswarm/channels/web/frontend run test:live-voice-integrated-web
npm --prefix jiuwenswarm/channels/web/frontend run build
```

Expected: all commands PASS. Record exact counts and any pre-existing unrelated failures separately.

- [ ] **Step 2: Perform Tier-3 independent review**

Review spec coverage, type consistency between Python/TypeScript, feature-off zero allocation, negative matrices, fault injection, private sentinel surfaces, replay/idempotency, and zero forbidden effects. Fix findings and rerun affected suites before measurement.

- [ ] **Step 3: Document the private run setup**

Update `E2E_RUNBOOK.md` with the exact three backend variables, frontend flag, three URL query keys, five public input cases, cold/warm separation, raw private output rule, and report commands. State that runtime credentials/devices/providers/network must be verified locally and are not restored by Git.

- [ ] **Step 4: Create immutable clean-source run configs**

Create one warm and one cold `run.json` outside the repository. Bind each to `git rev-parse HEAD`, a clean product-code state, the same five profiles/input cases, Provider/model, browser/OS/runtime classes, audio/VAD/playout config, route flags, and sample policy. Validate each with the CLI before starting JiuwenSwarm.

- [ ] **Step 5: Execute the real current-source baseline**

Run five attempted warm rounds per profile as a smoke iteration. Resolve probe defects only; if fixed segment definitions or instrumentation change, discard those results and start a new run. Then collect at least 20 successful warm rounds and at least 20 successful cold rounds per profile, retaining every failed/fallback/cancelled/underrun/rebuffer attempt in the denominator.

- [ ] **Step 6: Generate and inspect reports**

Run `report` for warm and cold directories. Verify every Browser fixed segment and both totals, expected Gateway/Agent drill-downs, explicit unknowns, no cross-clock arithmetic, exact Git/config binding, and zero forbidden content. Do not accept a baseline with missing required marks or unexplained failures.

- [ ] **Step 7: Record evidence and status without private data**

Write `LATENCY_BASELINE_MINIMAL_PROBE_V0.md` with commit, sanitized run-config fingerprint, environment class, sample/outcome counts, per-profile p50/p95, unknowns, guardrails, test/review evidence, and links to the private report location by opaque run ID only. Update the optimization plan to name this baseline as its oracle. Update `STATUS.md` from “instrumentation before optimization” only if all acceptance conditions passed; otherwise keep `PARTIAL` and state the exact gap.

- [ ] **Step 8: Commit documentation/evidence closure**

```bash
git add live-voice/runbooks/E2E_RUNBOOK.md live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md live-voice/STATUS.md live-voice/evidence/LATENCY_BASELINE_MINIMAL_PROBE_V0.md
git commit -m "docs(live-voice): record current latency baseline"
```

## Completion boundary

This plan is complete only when the default-off probe passes the automated and Tier-3 review requirements and the accepted clean-source warm/cold baseline exists. Completion establishes the measurement oracle for the next packet. It does not implement an optimization, pass a latency target, broaden P3/D1/D2, or establish product/Production readiness.
