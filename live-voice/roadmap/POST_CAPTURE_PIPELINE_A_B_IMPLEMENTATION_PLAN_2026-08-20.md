# Post-Capture Live Voice Pipeline A/B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a default-off, reproducible runner that feeds fixed audio into the real Browser Live Voice route without a microphone or manual UI actions, measures the pipeline from EOT through authoritative playout ACK, and produces compatible baseline/candidate reports.

**Architecture:** A fixture-backed `BrowserAudioEnvironment` supplies a memory-only `MediaStream` to the existing `ProductP1VoiceRouteOwner`; no transcript, speech receipt, Agent result or playout receipt is forged. A closed Browser controller starts one saved-session attempt from URL configuration, while a loopback Python runner serves the allowlisted WAV, launches the declared Browser command, observes a content-free terminal receipt and validates the formal probe shards. The latency manifest gains explicit track/lane/fixture identity so the existing reducer and comparison CLI cannot pool capture, post-capture, Browser, deterministic or physical populations.

**Tech Stack:** Python 3.11, `asyncio`, `http.server`, `subprocess`, `wave`, `hashlib`, React/TypeScript, Web Audio API, existing WebSocket RPC/media clients, pytest, Node test runner, TypeScript, esbuild, Ruff.

**Spec:** [fixed-audio benchmark methodology](FIXED_AUDIO_LATENCY_BENCHMARK_DRAFT_2026-08-19.md) §§2.1–2.2 and §10; [2026-08-20 experiment evidence](../evidence/LATENCY_EXPERIMENTS_2026-08-20.md) §§5–8.

## Global Constraints

- This is a Tier-3 shared-protocol, identity, authority and cross-module diagnostic packet under root `TESTING.md`; close every applicable `P/N/B/S/T/C/R/I/F/K/X` dimension and obtain one independent review.
- The implemented MVP track is exactly `post_capture_pipeline`, measured from `browser.eot_received`; it is not Track 1 capture/endpointing acceptance.
- The supported MVP lane is `controlled_browser_fixture`: a visible supported Chrome runtime with real WebAudio playout, but no OS microphone and no product-UI click sequence.
- The fixture stream may exercise capture to establish real media and Speech authority, but capture segments are diagnostic only and cannot be the experiment target in this track.
- Feature-off or absent/invalid query configuration performs zero fixture fetch, zero storage mutation, zero capture, zero Agent/Tool/Task/history mutation and zero probe export.
- The runner never mints a Speech receipt, Gateway claim, PresentationUnit, media receipt or P2 ACK. Existing owners must produce and validate each one.
- Raw WAV bytes and Browser-recognized text remain memory-only and outside probe events, result POSTs, logs and reports. The tracked/run-visible identity is only `fixture_profile_id` plus `input_case_id`.
- The first runner supports `dialogue_no_tool` and `dialogue_with_tool`. P3 Task create/status/cancel, background lifecycle, barge-in, degraded network and deterministic Agent fixtures are excluded from this packet.
- Baseline and candidate use separate clean worktrees, processes, Browser profiles, `JIUWENSWARM_DATA_DIR`, run IDs and output directories. The runner does not switch source trees inside a live process.
- Automated Track 2 evidence cannot replace Controlled Browser capture validation, physical first-audible evidence or final human product acceptance.
- Provider/model, network, Agent output and Tool results remain stochastic in the real-Agent profile. Use A/B/A and sufficient repetitions; do not claim an optimization from one smoke attempt.
- Existing user changes in `LiveVoiceIntegratedRoutePanel.tsx`, `pyproject.toml`, `uv.lock` and untracked documents must be preserved and reconciled before implementation touches an overlapping file.

## File and responsibility map

| Path | Responsibility |
|---|---|
| `jiuwenswarm/server/live_voice/latency_probe.py` | Backward-compatible run-manifest v1 track/lane/fixture identity and ordered profile subsets |
| `jiuwenswarm/server/live_voice/latency_probe_report.py` | Track-aware reduction/report/comparison compatibility and target validation |
| `tests/unit_tests/live_voice/test_latency_probe.py` | Closed manifest, compatibility and privacy tests |
| `tests/unit_tests/live_voice/test_latency_probe_report.py` | Track-specific reduction/comparison and CLI tests |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/fixedAudioCaptureEnvironment.ts` | Memory-only fixed-WAV `BrowserAudioEnvironment` owner |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/postCapturePipelineBenchmark.ts` | Closed query, one-attempt state machine and content-free runner receipt |
| `jiuwenswarm/channels/web/frontend/tests/liveVoiceFixedAudioCaptureEnvironment.test.mjs` | WAV/environment lifecycle and fault tests |
| `jiuwenswarm/channels/web/frontend/tests/liveVoicePostCapturePipelineBenchmark.test.mjs` | Query/state/receipt/default-off tests |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/latencyProbe.ts` | Optional diagnostic-only batch-settlement observer |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts` | Injection of an already-validated `BrowserAudioEnvironment`; no benchmark branch in business methods |
| `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx` | Default-off construction and start of the Browser benchmark controller on the real product owners |
| `jiuwenswarm/channels/web/frontend/src/featureFlags.ts` | Default-off build flag |
| `jiuwenswarm/channels/web/frontend/src/vite-env.d.ts` | Build-flag typing |
| `jiuwenswarm/channels/web/frontend/package.json` | Focused frontend test command |
| `jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs` | Product-owner parity and zero-bypass tests |
| `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs` | Controller seam tests |
| `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs` | Mounted real-owner attempt and feature-off tests |
| `scripts/live_voice/post_capture_latency_runner.py` | Strict fixture server, Browser launcher, attempt supervisor and artifact gate |
| `tests/unit_tests/live_voice/test_post_capture_latency_runner.py` | Runner contract, lifecycle, privacy and failure tests |
| `live-voice/runbooks/E2E_RUNBOOK.md` | Exact development commands and limitations after implementation passes |
| `live-voice/STATUS.md` | One concise capability-row update only after a real clean automated run succeeds |

---

### Task 1: Add explicit post-capture run identity without breaking v0 evidence

**Risk:** Tier 3 — closed persisted protocol and comparison compatibility.

**Files:**
- Modify: `jiuwenswarm/server/live_voice/latency_probe.py:28-177`
- Modify: `jiuwenswarm/server/live_voice/latency_probe.py:328-420`
- Modify: `jiuwenswarm/server/live_voice/latency_probe.py:739-815`
- Modify: `jiuwenswarm/server/live_voice/latency_probe_report.py:620-715`
- Test: `tests/unit_tests/live_voice/test_latency_probe.py`
- Test: `tests/unit_tests/live_voice/test_latency_probe_report.py`

**Interfaces:**
- Produces: `RUN_SCHEMA_VERSION_V1 = "live-voice.latency-run.v1"`.
- Produces: `OptimizationTrack = Literal["capture_endpointing", "post_capture_pipeline", "legacy_full_journey"]`.
- Produces: `BenchmarkLane = Literal["controlled_browser_fixture", "controlled_browser", "physical_journey", "legacy_unspecified"]`.
- Extends: `LatencyRunConfig.optimization_track: str`, `benchmark_lane: str`, `fixture_profile_id: str`.
- Preserves: parsing and re-serialization of existing v0 manifests as `legacy_full_journey` / `legacy_unspecified` without rewriting their `schema_version`.
- Consumed by Tasks 3, 5 and 6 through `run.to_dict()` and `load_latency_run_config()`.

- [ ] **Step 1: Write RED tests for v1, v0 compatibility and profile subsets**

Add a `valid_v1_run_json()` helper and tests with exact assertions:

```python
def valid_v1_run_json() -> dict[str, object]:
    value = valid_run_json()
    value.update(
        schema_version="live-voice.latency-run.v1",
        optimization_track="post_capture_pipeline",
        benchmark_lane="controlled_browser_fixture",
        fixture_profile_id="en-v1-fixed-wav",
        profile_ids=["dialogue_no_tool", "dialogue_with_tool"],
        input_case_ids=["dialogue-paris-en-v1", "tool-weather-en-v1"],
    )
    return value


def test_v1_run_declares_post_capture_track_and_ordered_dialogue_subset(tmp_path):
    path = tmp_path / "run.json"
    path.write_text(json.dumps(valid_v1_run_json()), encoding="utf-8")

    run = load_latency_run_config(path)

    assert run.schema_version == "live-voice.latency-run.v1"
    assert run.optimization_track == "post_capture_pipeline"
    assert run.benchmark_lane == "controlled_browser_fixture"
    assert run.fixture_profile_id == "en-v1-fixed-wav"
    assert run.profile_ids == ("dialogue_no_tool", "dialogue_with_tool")
    assert run.input_case_for_profile("dialogue_with_tool") == "tool-weather-en-v1"


def test_v0_run_remains_legacy_and_round_trips_without_v1_keys(run_config):
    assert run_config.optimization_track == "legacy_full_journey"
    assert run_config.benchmark_lane == "legacy_unspecified"
    assert "optimization_track" not in run_config.to_dict()
    assert run_config.to_dict()["schema_version"] == "live-voice.latency-run.v0"
```

Add parametrized rejections for an empty profile list, reordered canonical IDs, Task profiles in the MVP post-capture fixture profile, unknown track/lane, overlong fixture ID, sensitive descriptor names and extra keys.

- [ ] **Step 2: Run the focused RED tests**

Run:

```bash
uv run pytest \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py \
  -q
```

Expected: the new v1 tests fail because the keys and dataclass fields are absent; all pre-existing v0 tests remain green.

- [ ] **Step 3: Implement the versioned closed parser**

Implement separate key sets rather than making the v0 parser permissive:

```python
RUN_SCHEMA_VERSION_V0: Final = "live-voice.latency-run.v0"
RUN_SCHEMA_VERSION_V1: Final = "live-voice.latency-run.v1"
OPTIMIZATION_TRACKS: Final = (
    "capture_endpointing",
    "post_capture_pipeline",
)
BENCHMARK_LANES: Final = (
    "controlled_browser_fixture",
    "controlled_browser",
    "physical_journey",
)
_CONFIG_V1_KEYS: Final = _CONFIG_V0_KEYS | frozenset(
    {"optimization_track", "benchmark_lane", "fixture_profile_id"}
)
```

`LatencyRunConfig.to_dict()` must emit the three new keys only for v1. For v1, accept a non-empty ordered subsequence of canonical `PROFILE_IDS`, require matching input-case cardinality and reject Task profiles when `benchmark_lane == "controlled_browser_fixture"` in this MVP. Do not change context/mark/batch schema versions.

- [ ] **Step 4: Make report compatibility include the new identity**

Extend `_compatible()` with:

```python
"optimization_track",
"benchmark_lane",
"fixture_profile_id",
```

Explicitly reject v0/v1 comparison and reject `capture_endpointing` versus `post_capture_pipeline` even when every other descriptor matches.

- [ ] **Step 5: Run focused GREEN and static checks**

Run:

```bash
uv run pytest \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py \
  -q
uv run ruff check \
  jiuwenswarm/server/live_voice/latency_probe.py \
  jiuwenswarm/server/live_voice/latency_probe_report.py \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py
python -m py_compile \
  jiuwenswarm/server/live_voice/latency_probe.py \
  jiuwenswarm/server/live_voice/latency_probe_report.py
```

Expected: all commands exit 0.

- [ ] **Step 6: Review and commit Task 1**

Verify `git diff --check`, inspect the scoped diff and commit only these four files:

```bash
git add \
  jiuwenswarm/server/live_voice/latency_probe.py \
  jiuwenswarm/server/live_voice/latency_probe_report.py \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py
git commit -m "feat(live-voice): identify post-capture latency runs"
```

---

### Task 2: Build the fixed-WAV Browser audio environment

**Risk:** Tier 2 — Browser audio lifecycle, memory/privacy and capture timing; no product authority mutation by this module alone.

**Files:**
- Create: `jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/fixedAudioCaptureEnvironment.ts`
- Create: `jiuwenswarm/channels/web/frontend/tests/liveVoiceFixedAudioCaptureEnvironment.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Interfaces:**
- Produces:

```ts
export interface FixedAudioCaptureFixture {
  readonly input_case_id: string;
  readonly wav_bytes: ArrayBuffer;
  readonly expected_sample_rate_hz: number;
  readonly start_delay_ms: number;
}

export interface FixedAudioCaptureOwner {
  readonly environment: BrowserAudioEnvironment;
  readonly input_case_id: string;
  close(): Promise<void>;
}

export function createFixedAudioCaptureOwner(
  fixture: FixedAudioCaptureFixture,
  platform?: FixedAudioCapturePlatform,
): FixedAudioCaptureOwner;
```

- Consumed by Task 3 and injected into `ProductP1VoiceRouteOwner` by Task 4.
- The owner returns a synthetic `MediaStream` only through the existing `BrowserAudioEnvironment.mediaDevices.getUserMedia()` contract.

- [ ] **Step 1: Write RED tests for strict WAV and lifecycle ownership**

Cover these exact cases:

```js
test('fixed audio owner starts one memory-only stream after the declared lead', async () => {
  const platform = fakeFixedAudioPlatform({ sampleRate: 48_000 });
  const owner = createFixedAudioCaptureOwner({
    input_case_id: 'dialogue-paris-en-v1',
    wav_bytes: pcm16MonoWav({ sampleRate: 48_000, samples: [0, 100, -100, 0] }),
    expected_sample_rate_hz: 48_000,
    start_delay_ms: 1_000,
  }, platform);

  const stream = await owner.environment.mediaDevices.getUserMedia({ audio: true });

  assert.equal(stream, platform.stream);
  assert.deepEqual(platform.sourceStarts, [1.0]);
  await owner.close();
  assert.equal(platform.contextClosed, true);
  assert.equal(platform.tracksStopped, 1);
});
```

Add negative tests for non-RIFF bytes, non-PCM16, stereo, empty data, sample-rate mismatch, more than 4 MiB, second `getUserMedia`, start-delay outside `250..5_000`, source/context failure, close-before-start and double close. Assert error messages contain stable reason IDs but no input bytes or decoded text.

- [ ] **Step 2: Run the focused RED test**

Add package script `test:live-voice-fixed-audio-benchmark` that compiles with strict TypeScript, bundles with esbuild and runs the new Node test. Run it and observe module-not-found failure.

- [ ] **Step 3: Implement the bounded memory-only owner**

The implementation must:

- validate one canonical PCM16 mono WAV before calling WebAudio;
- create its own `AudioContext` and `MediaStreamAudioDestinationNode`;
- decode/copy the WAV into an `AudioBuffer` without persisting it;
- schedule exactly one source at `currentTime + start_delay_ms / 1000`;
- return only the destination stream from `getUserMedia`;
- report an authenticated-looking microphone permission status only inside this
  explicit benchmark environment, never through the default environment;
- stop the source/tracks and close the context on every terminal path;
- clear references to WAV/decoded buffers on close;
- never log or include WAV bytes in errors.

Use a private `closed` and `streamClaimed` latch; do not silently create a second source for retries.

- [ ] **Step 4: Run GREEN, formatting and diff checks**

Run:

```bash
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-fixed-audio-benchmark
npx prettier --check \
  src/features/live-voice/benchmark/fixedAudioCaptureEnvironment.ts \
  tests/liveVoiceFixedAudioCaptureEnvironment.test.mjs
cd ../../../..
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 5: Review and commit Task 2**

```bash
git add \
  jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/fixedAudioCaptureEnvironment.ts \
  jiuwenswarm/channels/web/frontend/tests/liveVoiceFixedAudioCaptureEnvironment.test.mjs \
  jiuwenswarm/channels/web/frontend/package.json
git commit -m "feat(live-voice): add fixed audio benchmark input"
```

---

### Task 3: Add the closed one-attempt Browser benchmark controller

**Risk:** Tier 2 — automatic lifecycle and cross-attempt identity; controller remains diagnostic-only.

**Files:**
- Create: `jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/postCapturePipelineBenchmark.ts`
- Create: `jiuwenswarm/channels/web/frontend/tests/liveVoicePostCapturePipelineBenchmark.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/latencyProbe.ts`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceLatencyProbe.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Interfaces:**
- Consumes: `createFixedAudioCaptureOwner()` from Task 2.
- Produces:

```ts
export type PostCaptureBenchmarkPhase =
  | 'waiting_for_session'
  | 'loading_fixture'
  | 'waiting_for_activation'
  | 'running'
  | 'exporting'
  | 'completed'
  | 'failed';

export interface PostCaptureBenchmarkConfig {
  readonly run_id: string;
  readonly profile_id: 'dialogue_no_tool' | 'dialogue_with_tool';
  readonly input_case_id: string;
  readonly round_index: number;
  readonly session_id: string;
  readonly fixture_url: string;
  readonly result_url: string;
  readonly start_delay_ms: number;
}

export function parsePostCaptureBenchmarkConfig(
  enabled: boolean,
  location: Pick<Location, 'search' | 'origin' | 'pathname'>,
): PostCaptureBenchmarkConfig | null;
```

- Extends `createBrowserLatencyProbe` options with an optional
  `onBatchSettled(batch, receipt)` observer invoked after exact successful or
  terminally unknown export; it cannot change export or product outcome.
- Produces `PostCaptureBenchmarkController.start(control)` where `control.start`
  and `control.close` are the existing real product controls supplied by Task 4.

- [ ] **Step 1: Write RED query and default-off tests**

The parser must accept only:

```text
?live_voice_post_capture_benchmark=1
&run_id=run-20260820-a
&profile_id=dialogue_no_tool|dialogue_with_tool
&input_case_id=dialogue-paris-en-v1
&round_index=0
&session_id=web_benchmark_session
&fixture_url=http://127.0.0.1:41731/fixture/dialogue-paris-en-v1.wav
&result_url=http://127.0.0.1:41731/result
&start_delay_ms=1000
```

Test feature-off with throwing `location.search`, `fetch`, storage and clock
spies; every spy count must remain zero. Reject unknown/duplicate query keys,
non-loopback URLs, mixed fixture/result origins, fragments, credentials in URLs,
case/path mismatch, wrong pathname session, overlong tokens and non-canonical
integers. The accepted `round_index` range is `0..255` and the accepted
`start_delay_ms` range is `250..5000`.

- [ ] **Step 2: Write RED state-machine and receipt tests**

Use fakes to prove:

- one valid config fetches the exact WAV once and calls product `start()` once;
- only a completed batch matching run/profile/case/round/session posts
  `{schema_version, run_id, profile_id, input_case_id, round_index, outcome}`;
- foreign, duplicate, stale and accessor-bearing batches do not complete;
- timeout/fetch/audio/product/export failures post only a stable reason ID;
- result POST failure terminates unknown locally and is not retried as a product
  action;
- `close()` is always invoked once after completion/failure;
- no result contains transcript, prompt, WAV bytes, response text, credentials,
  endpoint details or exception text.

- [ ] **Step 3: Run RED**

Run the new package test and the existing latency-probe test. Expected: new
module/interface failures while the old latency tests stay green.

- [ ] **Step 4: Implement the controller and post-export observer**

Use a single `AbortController`, a monotonic phase transition table and a
one-shot terminal latch. The controller may observe diagnostics but must not
call unified submit, TTS, media ACK or P2 presentation ACK directly. Those
remain owned by the product route.

The latency observer receives a deeply frozen batch snapshot and a closed
receipt:

```ts
type BrowserLatencyBatchSettlement = Readonly<{
  disposition: 'written' | 'idempotent' | 'unknown';
}>;
```

Observer exceptions are contained after export settlement and cannot change
the batch receipt.

- [ ] **Step 5: Run GREEN and focused regressions**

Run:

```bash
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-post-capture-benchmark
npm run test:live-voice-latency-probe
npx prettier --check \
  src/features/live-voice/benchmark/postCapturePipelineBenchmark.ts \
  src/features/live-voice/formal/latencyProbe.ts \
  tests/liveVoicePostCapturePipelineBenchmark.test.mjs \
  tests/liveVoiceLatencyProbe.test.mjs
cd ../../../..
git diff --check
```

- [ ] **Step 6: Review and commit Task 3**

Commit only the controller, latency observer, their tests and the package script:

```bash
git commit -m "feat(live-voice): control post-capture benchmark rounds"
```

---

### Task 4: Wire the controller to the unchanged formal product owners

> **Progress — 2026-08-20:** implemented in `8fb766314`. The default-off
> Panel composition now validates the closed benchmark query, binds the exact
> active Session and visible page, derives the Browser probe selection from
> that accepted configuration, injects the fixed-WAV environment through the
> existing `ProductP1VoiceRouteOwner.audio_environment` seam, observes only a
> settled Browser batch, and closes P1 before the fixture owner. Focused fixed
> audio, controller, probe, Browser audio, complete Integrated Web automation
> (409 tests), and the production frontend build passed. The external
> reviewer-requested mounted true-flag journey, full Tier-3 negative matrix and
> independent review remain acceptance work; this commit alone does not grant
> automated-baseline or product-readiness credit.

**Risk:** Tier 3 — automatic Agent/Tool/history/audio effects on the real route.

**Files:**
- Modify: `jiuwenswarm/channels/web/frontend/src/featureFlags.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/vite-env.d.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts:305-434`
- Modify: `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx:1280-1400`
- Modify: `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx:3300-3650`
- Test: `jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs`
- Test: `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs`
- Test: `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs`

**Interfaces:**
- Adds default-off `FEATURE_LIVE_VOICE_POST_CAPTURE_BENCHMARK` from
  `VITE_FEATURE_LIVE_VOICE_POST_CAPTURE_BENCHMARK`.
- `ProductP1VoiceRouteOwner` continues to consume only the existing optional
  `audio_environment`; no benchmark boolean or alternate submit/playout method
  is added to the owner.
- Panel creates the Task 2 environment and Task 3 controller only after the
  feature flag and query parse successfully.

- [ ] **Step 1: Write RED feature-off and invalid-query mounted tests**

Compile the panel with the flag absent/false and assert zero fixture fetch,
zero `ProductP1VoiceRouteOwner`, zero `live_voice.media.activate`, zero Speech,
zero unified submit, zero TTS and zero storage change even if the URL contains
benchmark-looking parameters.

With the build flag true but invalid query, assert the same zero effects and
ordinary manual Live Voice availability remains unchanged.

- [ ] **Step 2: Write RED real-owner positive journey**

Use the mounted real `ProductP2WebActivationOwner`,
`ProductP1VoiceRouteOwner`, `ProductUnifiedCommittedInputOwner` and
`BrowserLatencyProbe`. Only transport/provider/media implementations may be
faked. Assert the exact order:

```text
P2 activate
→ fixture-backed capture/media authority
→ EOT
→ formal Speech final and Gateway receipt
→ unified.submit
→ Agent notification/final PresentationUnit
→ TTS
→ downlink first frame
→ WebAudio schedule/render complete
→ media playout receipt
→ P2 presentation ACK
→ latency batch export
→ content-free runner result
→ product close
```

Assert a single user/history turn, one response generation and one audible
generation. No benchmark code may directly manufacture the receipt or ACK.

- [ ] **Step 3: Write RED Tier-3 negative matrix**

Cover:

- `N/B`: malformed query/WAV/result URL and over-capacity input;
- `S/T`: page reload, stale activation, stale round, duplicate result and late
  Agent/TTS/downlink events;
- `C`: start/stop race and two tabs targeting one round;
- `R`: Browser crash before export and result POST loss;
- `I`: wrong session/case/run/activation/response binding;
- `F`: flag off, Provider fallback, TTS failure, hidden page and underrun;
- `K`: ordinary manual Live Voice tests remain unchanged;
- `X`: actual mounted formal-owner seam, with deterministic providers clearly
  labeled as test evidence.

For every rejected/stale path assert zero wrong Agent, Tool, Task, history,
audio, ACK, other-session and probe-slot effects.

- [x] **Step 4: Implement the smallest Panel-only composition**

At component initialization:

1. parse config only when the build flag is true;
2. require `props.activeSessionId === config.session_id`;
3. fetch and construct the fixed-audio owner;
4. pass `owner.environment` through the existing `audio_environment` constructor
   option;
5. start only after P2 is active, no retained operation exists and document
   visibility is `visible`;
6. let the existing EOT handler and product loop own every later transition;
7. finish from the exact exported Browser batch;
8. close controller, audio owner and product owner in reverse ownership order.

Do not add a visible benchmark button or production fallback.

- [x] **Step 5: Run focused GREEN and frontend build**

Run:

```bash
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-fixed-audio-benchmark
npm run test:live-voice-post-capture-benchmark
npm run test:live-voice-latency-probe
npm run test:live-voice-browser-audio-io
npm run test:live-voice-integrated-web
npm run build
cd ../../../..
git diff --check
```

Expected: all focused tests and build exit 0; pre-existing build warnings are
recorded but do not hide new warnings/errors.

- [ ] **Step 6: Independent Tier-3 review and commit Task 4**

Request an independent review over the complete Task 2–4 diff, fix findings,
repeat affected tests and record the review result. Then commit only the
frontend integration scope:

```bash
git commit -m "feat(live-voice): automate fixed audio product rounds"
```

---

### Task 5: Create the loopback attempt runner and fixture server

> **Progress — 2026-08-20:** the supervised runner was implemented in
> `b8d3ebc4c`. It validates bounded PCM16 mono fixtures and hashes, rechecks the
> hash at serving time, binds only loopback HTTP/CORS, accepts one exact
> content-free result, launches an optional Browser argv with `shell=False`,
> owns bounded cleanup, requires exact Browser/STT/TTS/Agent shards, supports
> repeated rounds without confusing aggregate report counts, and writes the v1
> report. The source-fact correction also makes the reducer accept both v0 and
> v1 manifests. Focused runner/probe/report automation passed 161 tests plus
> Ruff, `py_compile`, and diff checks. Complete Tier-2 matrix review and a real
> automated Browser smoke remain open; no baseline credit is granted yet.

**Risk:** Tier 2 — process lifecycle, private paths and diagnostic result integrity; it invokes the Tier-3 product route but owns no product authority.

**Files:**
- Create: `scripts/live_voice/post_capture_latency_runner.py`
- Create: `tests/unit_tests/live_voice/test_post_capture_latency_runner.py`

**Interfaces:**
- Consumes Task 1 `run.json` v1 and an external private fixture manifest.
- Serves exact loopback endpoints:
  - `GET /fixture/{input_case_id}.wav`
  - `POST /result`
- CLI:

```text
python scripts/live_voice/post_capture_latency_runner.py prepare-run
  --output /abs/runs/run-20260820-a/run.json
  --git-commit 0123456789abcdef0123456789abcdef01234567
  --source-state clean
  --fixture-profile-id en-v1-fixed-wav
  --profile-id dialogue_no_tool
  --input-case-id dialogue-paris-en-v1
  --environment-profile windows-chrome-wsl2
  --browser-profile chrome-150-windows
  --browser-os-class windows-11
  --gateway-profile wsl2-python-3.11
  --agent-profile wsl2-python-3.11
  --stt-profile openai-gpt-4o-mini-transcribe
  --tts-profile openai-gpt-4o-mini-tts-marin
  --audio-profile pcm16-48000-mono
  --vad-profile openai-server-vad-1200ms
  --playout-profile webaudio-lead-1000ms
  --cold-or-warm warm
  --intended-attempts 1
  --required-successes 1
  [--experiment-json /abs/private/experiment.json]

python scripts/live_voice/post_capture_latency_runner.py run
  --run-json ABSOLUTE_RUN_JSON
  --fixture-manifest ABSOLUTE_FIXTURE_JSON
  --profile-id dialogue_no_tool|dialogue_with_tool
  --round-index 0
  --session-id web_...
  --web-origin http://localhost:5173
  --browser-command-json '["/path/to/chrome","--user-data-dir=/abs/profile","{url}"]'
  --timeout-seconds 120
```

- Produces exit `0` only after matching Browser/Gateway/Agent shards and one
  completed content-free result; exits `2` for closed input/config errors and
  `3` for an executed failed/unknown attempt.

- [ ] **Step 1: Write RED closed fixture-manifest tests**

Use this exact private manifest shape:

```json
{
  "schema_version": "live-voice.fixed-audio-fixture.v0",
  "fixture_profile_id": "en-v1-fixed-wav",
  "cases": [
    {
      "profile_id": "dialogue_no_tool",
      "input_case_id": "dialogue-paris-en-v1",
      "wav_path": "pcm48k/dialogue-paris-en-v1.wav",
      "sha256": "e37d2f1eb21ac3bfe61048b3e4f246c2775432b606742dc0bdbcaa57f84dde3c",
      "sample_rate_hz": 48000
    }
  ]
}
```

Tests must reject unknown keys, duplicate profile/case, traversal, symlink
escape, absolute `wav_path`, wrong hash, non-PCM16/mono WAV, sample-rate
mismatch, oversized file and run/fixture profile mismatch. Error output names
only stable fields/reasons, never file bytes or transcript text.

- [ ] **Step 2: Write RED HTTP and Browser process tests**

With a fake `subprocess.Popen`, verify:

- server binds only `127.0.0.1` on an OS-assigned port;
- fixture GET requires exact case path and exact configured Web `Origin`;
- result POST requires exact JSON keys and run/profile/case/round identity;
- CORS allows only the configured Web origin;
- browser command is a decoded JSON string array, uses no shell and replaces
  exactly one `{url}` token;
- timeout/interrupt terminates only the exact child process it created;
- pre-existing Browser mode (`--browser-command-json []`) prints the URL and
  supervises results without attempting process ownership;
- raw WAV, query URL and private paths never appear in logs.

Also test `prepare-run`: it must emit one complete v1 manifest, reject an
invalid commit shape, preserve the declared ordered profile/case lists and
refuse to overwrite an existing output file.

- [ ] **Step 3: Write RED artifact gates**

Create run directories with missing, duplicate, conflicting and correct shards.
The runner must require, for the exact round:

- one Browser `browser_round` batch with terminal `completed`;
- one applicable Gateway STT batch and one Gateway TTS batch;
- one Agent foreground batch;
- no `probe.capacity`, fallback, failure, cancellation, underrun or rebuffer;
- a report generated successfully after exporter drain.

It must not infer success from the HTTP result alone.

- [x] **Step 4: Implement the strict runner**

Use `ThreadingHTTPServer`, immutable dataclasses and `subprocess.Popen(argv,
shell=False)`. Validate the run with:

```bash
uv run python -m jiuwenswarm.server.live_voice.latency_probe_report \
  validate-run --run-json /abs/runs/run-20260820-a/run.json
```

On terminal result, wait for shard settlement, invoke `report --run-dir`, load
the report through the existing parser and check exact attempt outcome. Always
shutdown HTTP and owned Browser process in `finally`.

- [x] **Step 5: Run focused GREEN/static checks**

```bash
uv run pytest tests/unit_tests/live_voice/test_post_capture_latency_runner.py -q
uv run ruff check \
  scripts/live_voice/post_capture_latency_runner.py \
  tests/unit_tests/live_voice/test_post_capture_latency_runner.py
python -m py_compile scripts/live_voice/post_capture_latency_runner.py
git diff --check
```

- [ ] **Step 6: Review and commit Task 5**

```bash
git add \
  scripts/live_voice/post_capture_latency_runner.py \
  tests/unit_tests/live_voice/test_post_capture_latency_runner.py
git commit -m "feat(live-voice): run supervised post-capture probes"
```

---

### Task 6: Close baseline/candidate comparison for the new track

> **Progress — 2026-08-20:** implemented in `b006f7644`. Post-capture targets
> are explicitly allowlisted, any dirty source is ineligible, and A/B/A requires
> B to improve against both baselines while A1→A2 latency and failure/
> denominator drift remain smaller than the minimum candidate gain. The central
> CLI emits one closed A/B/A JSON object; the runner compare mode invokes it
> with argv/`shell=False` and writes only a new explicit output. Cumulative
> probe/report/runner automation passed 169 tests plus Ruff, `py_compile`, and
> diff checks. Independent comparison review and real A/B/A evidence remain
> open; no optimization claim is granted.

**Risk:** Tier 3 — benchmark truth and optimization decision boundary.

**Files:**
- Modify: `jiuwenswarm/server/live_voice/latency_probe_report.py`
- Modify: `tests/unit_tests/live_voice/test_latency_probe_report.py`
- Modify: `scripts/live_voice/post_capture_latency_runner.py`
- Modify: `tests/unit_tests/live_voice/test_post_capture_latency_runner.py`

**Interfaces:**
- Adds CLI command:

```text
latency_probe_report compare-a-b-a
  --baseline-before REPORT_A1
  --candidate REPORT_B
  --baseline-after REPORT_A2
```

- Produces a closed JSON result containing A1/B/A2 comparison statuses and
  baseline drift per segment. It does not add statistics beyond existing
  p50/p95/delta/rate fields.

- [ ] **Step 1: Write RED compatibility and drift tests**

Test that comparison rejects or returns `inconclusive` for:

- different optimization track/lane/fixture profile;
- different profile order/case IDs/cold-warm/provider/playout/config flags;
- dirty source;
- target segment in capture-only stages for `post_capture_pipeline`;
- missing first-audio or response-total samples;
- semantic/failure denominator mismatch;
- A1→A2 drift larger than the candidate's claimed gain.

Use a valid positive case targeting `tts_request_to_first_downlink` with
`response_total` non-regression and zero fallback/underrun/rebuffer regression.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit_tests/live_voice/test_latency_probe_report.py -q
```

Expected: failures for absent track-aware target validation and A/B/A command.

- [x] **Step 3: Implement target allowlist and A/B/A composition**

Define an explicit post-capture target set:

```python
POST_CAPTURE_TARGET_SEGMENTS: Final = frozenset(
    {
        "eot_to_stt_final",
        "stt_final_to_submit",
        "submit_to_presentation",
        "presentation_to_tts_request",
        "tts_request_to_first_downlink",
        "first_downlink_to_schedule",
        "schedule_to_start_estimate",
        "playout_to_ack",
        "response_total",
    }
)
```

Do not allow capture startup/first-frame targets in this track. A/B/A is
`improved` only when B improves compatibly against both A1 and A2 and A1/A2
drift is smaller than the minimum B gain; otherwise return `inconclusive` or
`regressed` using stable reason IDs.

- [x] **Step 4: Add runner comparison mode**

Add a `compare` subcommand to the runner that validates three report paths,
calls the module CLI without shell invocation and writes no output beside the
explicit `--output` path. It must never start services or Browser in compare
mode.

- [x] **Step 5: Run GREEN and complete Python regression**

```bash
uv run pytest \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py \
  tests/unit_tests/live_voice/test_post_capture_latency_runner.py \
  -q
uv run ruff check \
  jiuwenswarm/server/live_voice/latency_probe.py \
  jiuwenswarm/server/live_voice/latency_probe_report.py \
  scripts/live_voice/post_capture_latency_runner.py \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py \
  tests/unit_tests/live_voice/test_post_capture_latency_runner.py
git diff --check
```

- [ ] **Step 6: Independent comparison review and commit Task 6**

Perform an independent cold review of manifest compatibility, denominators,
drift classification and malformed-report handling. Fix findings, rerun the
affected commands and commit:

```bash
git commit -m "feat(live-voice): compare post-capture A B A runs"
```

---

### Task 7: Verify one clean automated warm smoke and document execution

> **Progress — 2026-08-20:** operational setup, run, report, cleanup and A/B/A
> commands are documented in `E2E_RUNBOOK.md` §7.7. Follow-up commit
> `7074e10b2` makes candidate preparation accept a validated private
> `--experiment-json` and binds the Browser URL to the real
> `/chat/<session_id>` route. The current worktree still contains unrelated
> product-code changes and the user deferred the real baseline run; therefore a
> truthful clean automated smoke, failure journey, sanitized evidence, STATUS
> smoke credit and final independent Tier-3 review all remain open.

**Risk:** Tier 3 real-path evidence, but not physical acceptance.

**Files:**
- Modify: `live-voice/runbooks/E2E_RUNBOOK.md`
- Modify only after successful clean smoke: `live-voice/STATUS.md`
- Create after successful clean smoke: `live-voice/evidence/POST_CAPTURE_PIPELINE_SMOKE_20260820.md`

**Interfaces:**
- Consumes all previous tasks.
- Produces exact commands for a single-worktree run and A/B/A comparison.
- Does not implement or accept a latency optimization.

- [ ] **Step 1: Run cumulative automation from a clean implementation commit**

Run the three Python suites, all five focused frontend commands from Tasks 2–4,
the complete Integrated Web command, frontend build, Ruff, `py_compile` and
`git diff --check`. Record exact counts and HEAD only in the scoped evidence,
not STATUS.

- [ ] **Step 2: Prepare one truthful v1 warm run**

Create a fresh run directory and use the Task 5 `prepare-run` command with the
resolved implementation HEAD:

```bash
RUN_DIR=/abs/runs/post-capture-smoke-20260820
uv run python scripts/live_voice/post_capture_latency_runner.py prepare-run \
  --output "$RUN_DIR/run.json" \
  --git-commit "$(git rev-parse HEAD)" \
  --source-state clean \
  --fixture-profile-id en-v1-fixed-wav \
  --profile-id dialogue_no_tool \
  --input-case-id dialogue-paris-en-v1 \
  --environment-profile windows-chrome-wsl2 \
  --browser-profile chrome-150-windows \
  --gateway-profile wsl2-python-3.11 \
  --agent-profile wsl2-python-3.11 \
  --stt-profile openai-gpt-4o-mini-transcribe \
  --tts-profile openai-gpt-4o-mini-tts-marin \
  --audio-profile pcm16-48000-mono \
  --vad-profile openai-server-vad-1200ms \
  --playout-profile webaudio-lead-1000ms \
  --cold-or-warm warm \
  --intended-attempts 1 \
  --required-successes 1
```

Before execution, replace only a profile argument whose inspected runtime value
differs and record the resolved command in evidence. `prepare-run` supplies the
fixed `post_capture_pipeline` track and `controlled_browser_fixture` lane and
validates the complete emitted manifest.

- [ ] **Step 3: Execute one automated no-Tool attempt**

Start the normal JiuwenSwarm services with the formal route and probe enabled,
using a disposable no-remote Code project and isolated private state. Invoke
the runner for `dialogue_no_tool` with the supported visible Chrome command. No
microphone selection or product UI click is allowed. The runner supports the
`dialogue_with_tool` profile, but a real Tool smoke is a separate population
because the current `tool-git-status-en-v1` case can require interactive Tool
permission; it cannot block proof of the Live Voice-only runner.

Expected:

- exact fixture identity and semantic result pass;
- Browser, Gateway and Agent batches settle;
- TTS plays through real WebAudio while the page remains visible;
- media and P2 ACKs are authoritative;
- report command succeeds;
- no P3 Task mutation occurs;
- raw audio/transcript/credentials remain absent from JSONL, report and logs.

- [ ] **Step 4: Exercise one failure without forbidden effects**

Repeat with a fixture hash mismatch or hidden page. The runner must exit nonzero
with the stable reason, retain the failed attempt in the denominator and prove
zero Agent/Tool/Task/history/audio-ACK effects beyond the exact failure boundary.

- [ ] **Step 5: Write sanitized smoke evidence and runbook commands**

The evidence must state:

- exact clean product and Agent-Core commits;
- v1 track/lane/fixture profile;
- Browser/runtime/provider classes without private endpoints;
- commands, attempt outcomes and artifact basenames;
- that the smoke is not a baseline, A/B result, capture acceptance or physical
  first-audible result;
- every failure or limitation encountered.

Update the runbook with setup, runner invocation, shutdown/drain, report and
compare commands. Link to the benchmark methodology instead of redefining its
decision rules.

- [ ] **Step 6: Update STATUS only if the clean smoke actually passes**

Add one concise sentence to the Observability/benchmark capability row: the
post-capture runner completed one clean automated warm smoke, while repeated
warm/cold baseline and capture/physical evidence remain open. Do not claim an
accepted baseline or optimization.

- [ ] **Step 7: Final cumulative Tier-3 review and documentation checks**

Review the complete implementation diff from `2f631e5ee`, run an independent
cross-module review, resolve every finding, repeat affected tests, resolve every
changed Markdown link and run:

```bash
git diff --check
test -z "$(git ls-files 'docs/zh/live-voice/**')"
```

- [ ] **Step 8: Commit the verified smoke/runbook batch**

Stage only the scoped runbook, evidence and justified STATUS line:

```bash
git commit -m "docs(live-voice): verify automated post-capture smoke"
```

## Final acceptance checklist

- [ ] v0 run/report evidence still parses and compares under its legacy identity.
- [ ] v1 post-capture runs declare track, lane and fixture profile explicitly.
- [ ] Feature-off and invalid query produce zero benchmark/product effects.
- [ ] Fixed WAV remains memory-only and is never copied into probe/report/log output.
- [ ] The real formal Speech receipt, Gateway claim, unified admission, Agent route, PresentationUnit, TTS, media receipt and P2 ACK are exercised.
- [ ] Capture metrics are not accepted as post-capture optimization targets.
- [ ] Browser playout is real WebAudio in a visible controlled Browser, not a byte-receipt proxy.
- [ ] One dialogue-no-Tool automated warm attempt completes on exact clean source; Tool population remains separately declared until its permission/corpus contract is runnable.
- [ ] One negative/failure attempt retains zero forbidden cross-scope effects.
- [ ] Baseline/candidate and A/B/A comparisons reject incompatible or dirty populations.
- [ ] No physical, capture-quality, P3, Production or optimization-completion claim is made.
- [ ] Focused/cumulative tests, frontend build, static checks, scoped diff review and independent Tier-3 review pass.
