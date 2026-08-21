# EOT/STT Settlement Overlap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure the current post-EOT settlement/result serialization with the existing latency probe and implement one early waiter with an authoritative join only when the 80 ms and 10% materiality gates pass.

**Architecture:** Extend the existing Browser/Gateway latency marks and report reducer; do not create another trace protocol. A no-Chrome Node benchmark composes the real `ProductP1VoiceRouteOwner` with deterministic media and Speech seams. Product and wire changes are conditional on A1 proving materiality.

**Tech Stack:** TypeScript, Node test runner, Python 3.11, pytest, existing Live Voice latency probe/report, dedicated media registry.

**Spec:** `live-voice/roadmap/EOT_STT_SETTLEMENT_OVERLAP_SPEC_2026-08-21.md`

> **Final closure:** complete A1 source
> `8e5dab8b8c6651b2be784cf103df9239a93814a0` produced 20/20 exact,
> cleanup-complete attempts with all ten marks and eight segments. The largest
> respective removable-gap/fraction p50 values were 0.880 ms and 0.015, so the packet is closed as
> `NO_MATERIAL_SERIAL_GAP`; Tasks 4–6 remain skipped.

## Global Constraints

- `ServerVadConfig.silence_duration_ms` remains exactly `1200`.
- Reuse `LatencyProbeRuntime`, existing correlation identities and report reduction; add no second event protocol.
- Browser, WebAudio, microphone, Agent, Tool, Task, TTS and product submission are forbidden effects in the causal runner.
- A product candidate is forbidden unless A1 has a removable serial-gap p50 at least 80 ms and a removable serial-gap-fraction p50 at least 10% of `EOT -> recognized final` in a declared fixture. The removable gap is `streaming result returned - max(uplink closed, Provider final ready)`; route-settled-to-result-returned is diagnostic only.
- A result becomes visible only after both local uplink settlement and the matching Provider final succeed.
- Preserve the current `live_voice.speech.recognize_streaming_result` path byte-for-byte while the candidate is off.

---

### Task 1: Extend the existing latency probe at the missing waiter boundaries — COMPLETE

**Files:**
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/latencyProbe.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`
- Modify: `jiuwenswarm/server/live_voice/latency_probe.py`
- Modify: `jiuwenswarm/server/live_voice/latency_probe_report.py`
- Test: `jiuwenswarm/channels/web/frontend/tests/liveVoiceLatencyProbe.test.mjs`
- Test: `jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs`
- Test: `tests/unit_tests/live_voice/test_latency_probe.py`
- Test: `tests/unit_tests/live_voice/test_latency_probe_report.py`

**Interfaces:**
- Consumes: existing `BrowserLatencyRound.mark()` and `LatencyProbeRuntime` batch ingestion.
- Produces: core points `browser.streaming_result_request_started` and `browser.streaming_result_returned`; segments `streaming_result_wait`, `streaming_result_validation`, and `uplink_settled_to_stt_final`.

- [x] **Step 1: Add RED point-catalog and report-segment tests**

```python
assert "browser.streaming_result_request_started" in CORE_POINTS_BY_COMPONENT["browser"]
assert "browser.streaming_result_returned" in CORE_POINTS_BY_COMPONENT["browser"]
assert _segment_by_id("streaming_result_wait").start_point == "browser.streaming_result_request_started"
assert _segment_by_id("streaming_result_wait").end_point == "browser.streaming_result_returned"
assert _segment_by_id("streaming_result_validation").end_point == "browser.stt_final_received"
```

Add the corresponding Node assertions that both new names are members of `BROWSER_LATENCY_CORE_POINTS` and reject duplicate/private observations exactly like existing core points.

- [x] **Step 2: Run the RED tests**

```bash
uv run pytest tests/unit_tests/live_voice/test_latency_probe.py tests/unit_tests/live_voice/test_latency_probe_report.py -q --no-cov
cd jiuwenswarm/channels/web/frontend && npm run test:live-voice-latency-probe
```

Expected: fail because the two points and derived segments are absent.

- [x] **Step 3: Add only the missing points and segments**

```typescript
export const BROWSER_LATENCY_CORE_POINTS = Object.freeze([
  // existing points remain in their current order
  'browser.streaming_result_request_started',
  'browser.streaming_result_returned',
] as const);
```

```python
_segment(
    "streaming_result_wait",
    "browser.streaming_result_request_started",
    "browser.streaming_result_returned",
    "browser",
    ("P1", "P2"),
    "speech_recognition",
)
```

Add `streaming_result_validation` from returned to `browser.stt_final_received` and `uplink_settled_to_stt_final` from `browser.uplink_closed` to `browser.stt_final_received`.

- [x] **Step 4: Mark the exact existing request without changing its order**

```typescript
this.#markLatency(latencyRound, 'browser.streaming_result_request_started');
const streaming = await speech.recognizeStreamingFinal(recognitionInput);
this.#markLatency(latencyRound, 'browser.streaming_result_returned');
this.#requireCurrent(operationGeneration);
```

The current `browser.stt_final_received` remains the accepted/validated product boundary.

- [x] **Step 5: Run GREEN and focused regressions**

```bash
uv run pytest tests/unit_tests/live_voice/test_latency_probe.py tests/unit_tests/live_voice/test_latency_probe_report.py -q --no-cov
cd jiuwenswarm/channels/web/frontend && npm run test:live-voice-latency-probe && npm run test:live-voice-integrated-web
```

Expected: all selected tests pass and the legacy recognition order is unchanged.

- [x] **Step 6: Commit Task 1**

```bash
git add jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/latencyProbe.ts jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts jiuwenswarm/server/live_voice/latency_probe.py jiuwenswarm/server/live_voice/latency_probe_report.py jiuwenswarm/channels/web/frontend/tests/liveVoiceLatencyProbe.test.mjs jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs tests/unit_tests/live_voice/test_latency_probe.py tests/unit_tests/live_voice/test_latency_probe_report.py
git commit -m "test(live-voice): expose EOT result wait boundaries"
```

### Task 2: Add the candidate-neutral A1 causal benchmark — COMPLETE

**Files:**
- Create: `jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/eotSttSettlementBenchmark.ts`
- Create: `jiuwenswarm/channels/web/frontend/tests/liveVoiceEotSttSettlementBenchmark.test.mjs`
- Create: `jiuwenswarm/channels/web/frontend/scripts/liveVoiceEotSttSettlementBenchmark.mjs`
- Create: `scripts/live_voice/eot_stt_registry_fixture.py`
- Create: `tests/unit_tests/live_voice/test_eot_stt_registry_fixture.py`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Interfaces:**
- Consumes: real `ProductP1VoiceRouteOwner`, real
  `DedicatedMediaProductRegistry.streaming_recognition_result`, existing
  Browser latency marks and deterministic audio/media/Provider dependencies.
- Produces: `runEotSttSettlementBenchmark(config): Promise<EotSttBenchmarkReport>` and a mode-600 JSON report containing closed per-attempt marks and p50/nearest-rank-p95 summaries.

- [x] **Step 1: Write RED validation and reduction tests**

```typescript
const fixtures = Object.freeze([
  { id: 'local-fast-provider-fast', localSettlementMs: 50, providerFinalMs: 50 },
  { id: 'local-slow-provider-fast', localSettlementMs: 500, providerFinalMs: 50 },
  { id: 'local-fast-provider-slow', localSettlementMs: 50, providerFinalMs: 500 },
  { id: 'both-slow', localSettlementMs: 500, providerFinalMs: 500 },
]);
const report = await runEotSttSettlementBenchmark({ fixtures, attempts: 5, candidate: 'A1' });
assert.equal(report.attempts.length, 20);
assert.equal(report.forbidden_effects.agent_submit, 0);
assert.equal(report.forbidden_effects.tts_request, 0);
assert.equal(report.summaries[0].successful_samples, 5);
```

Also assert rejection of duplicate fixture IDs, negative/nonfinite delay, attempts outside `1..20`, private transcript fields, overwrite, invalid source state and non-monotonic marks.

Add Python RED tests for a JSON-line fixture process whose exact result request
delegates to the real registry method. It must reject unknown operations and
private/extra fields, and it must expose only content-free timing/result facts.

- [x] **Step 2: Run RED**

```bash
cd jiuwenswarm/channels/web/frontend
npx tsc src/features/live-voice/benchmark/eotSttSettlementBenchmark.ts --target ES2020 --module ES2020 --moduleResolution Bundler --rootDir src/features/live-voice/benchmark --outDir node_modules/.cache/live-voice-eot-stt-benchmark --lib ES2020,DOM --skipLibCheck --noEmitOnError --strict --noUnusedLocals --noUnusedParameters
node --test tests/liveVoiceEotSttSettlementBenchmark.test.mjs
cd ../../../.. && uv run pytest tests/unit_tests/live_voice/test_eot_stt_registry_fixture.py -q --no-cov
```

Expected: compilation/test failure because the benchmark and registry fixture
owners are absent.

- [x] **Step 3: Implement the closed benchmark model and reducer**

```typescript
export interface EotSttFixture {
  readonly id: 'local-fast-provider-fast' | 'local-slow-provider-fast' | 'local-fast-provider-slow' | 'both-slow';
  readonly localSettlementMs: 50 | 500;
  readonly providerFinalMs: 50 | 500;
}

export interface EotSttAttempt {
  readonly fixture_id: EotSttFixture['id'];
  readonly attempt_index: number;
  readonly outcome: 'completed' | 'failed' | 'invalid';
  readonly marks_ms: Readonly<Record<string, number>>;
  readonly rpc_count: number;
  readonly exact_result: boolean;
  readonly cleanup_complete: boolean;
  readonly segments_ms: Readonly<Record<string, number | null>>;
  readonly removable_serial_gap_ms: number | null;
  readonly removable_serial_gap_fraction: number | null;
}
```

Use one monotonic clock, nearest-rank p95, exclusive file creation and `chmod(0o600)`. The report must contain no frames, transcript, item ID, exception text or credentials.
The closed mark set is the nine exact existing `browser.*` observations named
in the spec plus fixture-local `benchmark.provider_final_ready`; successful
attempts retain all eight spec segments, while unsuccessful attempts retain no
numeric segment or removable-gap credit.

- [x] **Step 4: Implement the real-registry fixture boundary**

`EotSttRegistryFixture` must build a `DedicatedMediaProductRegistry` using the
same exact authority/record factory as its focused tests. Its closed operations
are `open`, `provider_final`, `route_settled`, `streaming_result` and `close`.
The `streaming_result` operation calls the real
`registry.streaming_recognition_result(...)`; it does not reproduce that
method's authorization or payload logic.

```python
payload = await fixture.registry.streaming_recognition_result(
    params=fixture.exact_result_params,
    routed_session_id=fixture.session_id,
    connection_id=fixture.connection_id,
    request_origin=fixture.request_origin,
)
return {"status": payload["status"], "exact_result": fixture.is_exact(payload)}
```

The command process reads/writes one bounded JSON object per line, uses no
shell and closes every registry task. The fixed synthetic registry business
envelope may cross only captured in-memory child stdout for
`ProductP1VoiceRouteOwner` consumption; reports, error strings and terminal
output remain content-free and expose no transcript or identity value.

- [x] **Step 5: Compose the real Product P1 owner with the real registry seam**

The benchmark script must use the same owner factory pattern as `productP1VoiceRoute.test.mjs`. The Speech transport delays result readiness by `providerFinalMs`; the media leaf delays `completeUplink()` by `localSettlementMs`; both expose exact event callbacks to the existing latency round. The fixed text remains only in the captured fake/owner business exchange; persist only `exact_result=true` and content-free marks/segments.

Require an absolute `--python-executable` CLI value and start the fixture with
no shell:

```javascript
const fixture = spawn(
  pythonExecutable,
  [fixtureScript, '--local-settlement-ms', String(localMs), '--provider-final-ms', String(providerMs)],
  { shell: false, stdio: ['pipe', 'pipe', 'pipe'] },
);
```

`GatewaySpeechTransport.request()` exchanges the closed JSON-line records with
that process, so the final result envelope is produced by the real registry
implementation.

```javascript
const recognition = await owner.stopAndRecognize();
assert.equal(recognition.text, EXPECTED_TEXT);
assert.equal(effects.agent_submit, 0);
assert.equal(effects.tts_request, 0);
```

- [x] **Step 6: Add package commands and run GREEN**

```json
"test:live-voice-eot-stt-benchmark": "tsc src/features/live-voice/benchmark/eotSttSettlementBenchmark.ts --target ES2020 --module ES2020 --moduleResolution Bundler --rootDir src/features/live-voice/benchmark --outDir node_modules/.cache/live-voice-eot-stt-benchmark --lib ES2020,DOM --skipLibCheck --noEmitOnError --strict --noUnusedLocals --noUnusedParameters && node --test tests/liveVoiceEotSttSettlementBenchmark.test.mjs",
"benchmark:live-voice-eot-stt": "npm run test:live-voice-eot-stt-benchmark && node scripts/liveVoiceEotSttSettlementBenchmark.mjs"
```

```bash
cd jiuwenswarm/channels/web/frontend && npm run test:live-voice-eot-stt-benchmark
cd ../../../.. && uv run pytest tests/unit_tests/live_voice/test_eot_stt_registry_fixture.py -q --no-cov
```

- [x] **Step 7: Commit Task 2**

```bash
git add jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/eotSttSettlementBenchmark.ts jiuwenswarm/channels/web/frontend/tests/liveVoiceEotSttSettlementBenchmark.test.mjs jiuwenswarm/channels/web/frontend/scripts/liveVoiceEotSttSettlementBenchmark.mjs scripts/live_voice/eot_stt_registry_fixture.py tests/unit_tests/live_voice/test_eot_stt_registry_fixture.py jiuwenswarm/channels/web/frontend/package.json
git commit -m "test(live-voice): add EOT settlement materiality benchmark"
```

### Task 3: Run and decide A1 before touching the product protocol — COMPLETE (`NO_MATERIAL_SERIAL_GAP`)

**Files:**
- Create after run: `live-voice/evidence/EOT_STT_SETTLEMENT_MATERIALITY_RESULT_2026-08-21.md`
- Modify after run: `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`

**Interfaces:**
- Consumes: Task 2 benchmark at one exact clean commit.
- Produces: one of `NO_MATERIAL_SERIAL_GAP`, `JOIN_CANDIDATE_ELIGIBLE`, or `INCONCLUSIVE`.

- [x] **Step 1: Verify clean source and run A1**

```bash
test -z "$(git status --porcelain)"
git rev-parse HEAD
cd jiuwenswarm/channels/web/frontend
npm run benchmark:live-voice-eot-stt -- --output /tmp/live-voice-eot-stt-final-Up1qNe/eot-stt-a1-complete.json --git-commit 8e5dab8b8c6651b2be784cf103df9239a93814a0 --run-id eot-stt-complete-contract-final --attempts 5 --candidate A1 --python-executable /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-eot-stt-overlap/.venv/bin/python3
```

- [x] **Step 2: Apply the closed materiality rule**

```text
eligible = removable_serial_gap_p50_ms >= 80
           AND removable_serial_gap_fraction_p50 >= 0.10

removable_serial_gap_ms = streaming_result_returned
                          - max(uplink_closed, provider_final_ready)
removable_serial_gap_fraction = removable_serial_gap_ms
                                / (stt_final_received - eot_received)
```

Any failed/invalid attempt, incomplete cleanup or control inconsistency produces `INCONCLUSIVE`, not eligibility.
`route_settled_to_result_returned` remains diagnostic only and cannot authorize B.

- [x] **Step 3: Record sanitized evidence**

Record exact source commit, runner command, machine/runtime labels, all four fixture tables, p50/p95, RPC counts, zero forbidden effects and the closed decision. Do not copy raw JSON or private values into Git.

- [x] **Step 4: Commit the decision**

```bash
git add live-voice/evidence/EOT_STT_SETTLEMENT_MATERIALITY_RESULT_2026-08-21.md live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md
git commit -m "docs(live-voice): record EOT settlement materiality"
```

Result: all four removable p50/fraction pairs were below the 80 ms/0.10 gate;
the closed decision is `NO_MATERIAL_SERIAL_GAP`. Stop this plan here. Tasks
4–6 are skipped and forbidden.

Final exact result: 20/20 attempts retained all ten marks and eight segments;
the largest removable-gap p50 was 0.880 ms and the largest removable fraction
p50 was 0.015. See the
[sanitized result](../evidence/EOT_STT_SETTLEMENT_MATERIALITY_RESULT_2026-08-21.md).

### Task 4: Add the conditional Gateway early-wait join — SKIPPED (`NO_MATERIAL_SERIAL_GAP`)

**Files:**
- Modify: `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py`
- Test: `tests/unit_tests/gateway/test_streaming_speech_route.py`

**Interfaces:**
- Consumes: `JOIN_CANDIDATE_ELIGIBLE` evidence from Task 3.
- Produces: default-off `live_voice.speech.recognize_streaming_wait` with literal `protocol_version="live-voice.streaming-result-wait.v1"` and exact route/result join.

- [ ] **Step 1: Write RED authorization/order tests**

```python
waiter = asyncio.create_task(
    registry.streaming_recognition_wait(
        params={**exact_identity, "protocol_version": "live-voice.streaming-result-wait.v1"},
        routed_session_id="session-1",
        connection_id="connection-1",
        request_origin="http://localhost:5173",
    )
)
provider_final.set_result(completed_outcome)
await asyncio.sleep(0)
assert not waiter.done()
route_completed.set_result(None)
assert (await waiter)["status"] == "completed"
```

Add wrong version, stale generation, foreign connection, duplicate concurrent waiter, local failure, Provider failure-before-settlement, cancel/disconnect and late predecessor tests. Every negative test asserts zero returned text/fallback/receipt and clean bounded tasks.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit_tests/gateway/test_streaming_speech_route.py -q --no-cov -k 'streaming_recognition_wait'
```

- [ ] **Step 3: Implement the minimal default-off join**

Add one route-settlement future owned by `_MediaAuthority`; resolve it only on successful route completion and fail/cancel it on abort. The waiter may begin before `record.route_completed`, but must validate all exact identity/origin/activation facts first and return only after both futures succeed.

```python
provider_task = asyncio.create_task(_await_streaming_outcome(record))
settlement_task = asyncio.create_task(_await_route_settlement(record))
try:
    provider_outcome, _ = await asyncio.gather(provider_task, settlement_task)
except BaseException:
    for task in (provider_task, settlement_task):
        if not task.done():
            task.cancel()
    await asyncio.gather(provider_task, settlement_task, return_exceptions=True)
    raise
return self._streaming_result_payload(record, provider_outcome, exact_identity)
```

Reuse the current payload builder and timeout/fallback policy. Do not weaken `streaming_recognition_result()`.

- [ ] **Step 4: Run GREEN plus registry regressions**

```bash
uv run pytest tests/unit_tests/gateway/test_streaming_speech_route.py tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py -q --no-cov
uv run ruff check jiuwenswarm/gateway/live_voice/dedicated_media_registration.py tests/unit_tests/gateway/test_streaming_speech_route.py
```

- [ ] **Step 5: Commit Task 4**

```bash
git add jiuwenswarm/gateway/live_voice/dedicated_media_registration.py tests/unit_tests/gateway/test_streaming_speech_route.py
git commit -m "feat(live-voice): add bounded streaming result waiter"
```

### Task 5: Start the waiter early in Product P1 behind exact capability agreement — SKIPPED (`NO_MATERIAL_SERIAL_GAP`)

**Files:**
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`
- Test: `jiuwenswarm/channels/web/frontend/tests/liveVoiceGatewayBatchSpeech.test.mjs`
- Test: `jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs`

**Interfaces:**
- Consumes: Gateway wait method from Task 4.
- Produces: `recognizeStreamingWaitFinal(input, protocolVersion, signal)` and one authoritative `Promise.all([settleUplink, waitFinal])` join.

- [ ] **Step 1: Write RED Web protocol and join tests**

```javascript
const finalPromise = owner.stopAndRecognize();
await providerFinalReady();
assert.equal(await isSettled(finalPromise), false);
await localRouteSettlement();
assert.equal((await finalPromise).text, 'exact final');
assert.equal(calls.filter(call => call.method === WAIT_METHOD).length, 1);
```

Feature-off and capability-absent tests must assert the legacy method/order exactly. Add local-failure, Provider-failure, stale generation, disconnect and caller-cancel races.

- [ ] **Step 2: Run RED**

```bash
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-gateway-batch-speech
npm run test:live-voice-integrated-web
```

- [ ] **Step 3: Implement the early waiter and authoritative join**

After capture stop and final frame freeze, start one abort-bound waiter. Continue flush/last-ACK/`completeUplink()` concurrently. Validate and publish only after both branches settle.

```typescript
const waitController = new AbortController();
const resultPromise = speech.recognizeStreamingWaitFinal(
  recognitionInput,
  'live-voice.streaming-result-wait.v1',
  waitController.signal,
);
const settlementPromise = settleExactUplink();
try {
  const [, streaming] = await Promise.all([settlementPromise, resultPromise]);
  this.#requireCurrent(operationGeneration);
  result = requireExactStreamingResult(streaming, recognitionInput);
} catch (error) {
  waitController.abort();
  await Promise.allSettled([settlementPromise, resultPromise]);
  throw error;
}
```

- [ ] **Step 4: Run GREEN and TypeScript build**

```bash
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-gateway-batch-speech
npm run test:live-voice-integrated-web
npm run build
```

- [ ] **Step 5: Commit Task 5**

```bash
git add jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts jiuwenswarm/channels/web/frontend/tests/liveVoiceGatewayBatchSpeech.test.mjs jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs
git commit -m "perf(live-voice): overlap result wait with uplink settlement"
```

### Task 6: Run A1/B/A2, review and close the packet — SKIPPED (`NO_MATERIAL_SERIAL_GAP`)

**Files:**
- Modify: `live-voice/evidence/EOT_STT_SETTLEMENT_MATERIALITY_RESULT_2026-08-21.md`
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`
- Modify only if current truth changes: `live-voice/STATUS.md`

- [ ] **Step 1: Run the exact benchmark on A1, B and unchanged A2 source**

```bash
cd jiuwenswarm/channels/web/frontend
npm run benchmark:live-voice-eot-stt -- --candidate A1 --attempts 5 --python-executable /home/renan/openJiuwen-ai/jiuwenswarm/.venv/bin/python --output-root /home/renan/openJiuwen-ai/live-voice-latency-runs/eot-stt-a1
npm run benchmark:live-voice-eot-stt -- --candidate B --attempts 5 --python-executable /home/renan/openJiuwen-ai/jiuwenswarm/.venv/bin/python --output-root /home/renan/openJiuwen-ai/live-voice-latency-runs/eot-stt-b
npm run benchmark:live-voice-eot-stt -- --candidate A2 --attempts 5 --python-executable /home/renan/openJiuwen-ai/jiuwenswarm/.venv/bin/python --output-root /home/renan/openJiuwen-ai/live-voice-latency-runs/eot-stt-a2
```

- [ ] **Step 2: Apply the acceptance rules from the spec**

Require at least 80 ms and 10% p50 improvement against both controls in material fixtures, no p95 regression above 20 ms elsewhere, identical exact final/order, truthful failure/cleanup and zero forbidden effects.

- [ ] **Step 3: Run cumulative checks and independent Tier-2 review**

```bash
uv run pytest tests/unit_tests/gateway/test_streaming_speech_route.py tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py tests/unit_tests/live_voice/test_latency_probe.py tests/unit_tests/live_voice/test_latency_probe_report.py -q --no-cov
cd jiuwenswarm/channels/web/frontend && npm run test:live-voice-latency-probe && npm run test:live-voice-gateway-batch-speech && npm run test:live-voice-integrated-web && npm run build
git diff --check
```

Record the independent review, findings and affected reruns against the exact clean commit.

- [ ] **Step 4: Document and commit the closed decision**

```bash
git add live-voice/evidence/EOT_STT_SETTLEMENT_MATERIALITY_RESULT_2026-08-21.md live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md live-voice/STATUS.md
git commit -m "docs(live-voice): close EOT settlement experiment"
```
