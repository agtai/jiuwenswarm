# Semantic VAD Causal Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the current Streaming Speech and VAD benchmark owners to screen Provider-native Semantic VAD `auto` and `high` against the safe `server_vad=1200` control without Browser or another model RPC.

**Architecture:** Add one typed, feature-off Provider turn-detection mode and strict OpenAI wire validation. Reuse the existing `vad_eot_causal_benchmark.py`, corpus support, pacing, integrity, cleanup and report machinery; extend it with a closed mode/eagerness dimension rather than creating another probe system.

**Tech Stack:** Python 3.11, asyncio, OpenAI Realtime transcription WebSocket Adapter, pytest, existing Live Voice causal benchmark and latency probe concepts.

**Spec:** `live-voice/roadmap/SEMANTIC_VAD_CAUSAL_BENCHMARK_SPEC_2026-08-21.md`

## Global Constraints

- Begin only after the EOT/STT packet has a clean accepted/rejected/no-materiality closure.
- Product default remains `server_vad=1200`; no environment flag, Web setting or UI control is added.
- No additional semantic model call, RPC, socket or Provider session.
- `create_response` and `interrupt_response` are always `false`.
- Reuse the existing VAD benchmark/report and `LatencyProbeRuntime` boundaries; add no competing trace protocol.
- Failed, unknown, invalid, early-EOT or incomplete-transcript attempts contribute no latency sample.
- English-only evidence cannot authorize a global or Production default.

---

### Task 1: Add the closed typed Semantic VAD domain model

**Files:**
- Modify: `jiuwenswarm/server/live_voice/streaming_speech.py`
- Test: `tests/unit_tests/live_voice/test_streaming_speech.py`
- Test: `tests/unit_tests/live_voice/test_speech_ports.py`

**Interfaces:**
- Produces: `RecognitionTurnDetectionMode.SEMANTIC_VAD`, `SemanticVadEagerness`, `SemanticVadConfig`, `RecognitionTurnDetection.semantic_vad_configured(eagerness)`, and `RecognitionProviderSupport.semantic_vad`.
- Preserves: existing manual/Server VAD constructors and public disposition values.

- [ ] **Step 1: Write RED construction and compatibility tests**

```python
semantic = RecognitionTurnDetection.semantic_vad_configured(SemanticVadEagerness.AUTO)
assert semantic.mode is RecognitionTurnDetectionMode.SEMANTIC_VAD
assert semantic.semantic_vad == SemanticVadConfig(eagerness=SemanticVadEagerness.AUTO)
assert semantic.server_vad is None
assert RecognitionTurnDetection.server_vad_default().server_vad.silence_duration_ms == 1200
```

Reject raw strings, simultaneous Server/Semantic configs and either authority boolean set to true. Assert existing enum values and Server VAD dispositions are unchanged.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/live_voice/test_speech_ports.py -q --no-cov
```

- [ ] **Step 3: Implement the minimal immutable types**

```python
class SemanticVadEagerness(StrEnum):
    AUTO = "auto"
    HIGH = "high"

@dataclass(frozen=True, slots=True)
class SemanticVadConfig:
    eagerness: SemanticVadEagerness = SemanticVadEagerness.AUTO
    create_response: bool = False
    interrupt_response: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.eagerness, SemanticVadEagerness):
            raise StreamingSpeechViolation("INVALID_SEMANTIC_VAD", "semantic VAD eagerness is invalid")
        if self.create_response is not False or self.interrupt_response is not False:
            raise StreamingSpeechViolation("SEMANTIC_VAD_BUSINESS_AUTHORITY_FORBIDDEN", "Speech turn detection cannot create or interrupt Agent responses")
```

Make `RecognitionTurnDetection` enforce the exact one-of config relation and add a defaulted `semantic_vad` capability field with `UNAVAILABLE` provenance for compatibility.

- [ ] **Step 4: Run GREEN and static checks**

```bash
uv run pytest tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/live_voice/test_speech_ports.py -q --no-cov
uv run ruff check jiuwenswarm/server/live_voice/streaming_speech.py tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/live_voice/test_speech_ports.py
```

- [ ] **Step 5: Commit Task 1**

```bash
git add jiuwenswarm/server/live_voice/streaming_speech.py tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/live_voice/test_speech_ports.py
git commit -m "feat(live-voice): type semantic VAD configuration"
```

### Task 2: Add strict OpenAI Semantic VAD wire and echo handling

**Files:**
- Modify: `jiuwenswarm/server/live_voice/openai_streaming_speech.py`
- Test: `tests/unit_tests/live_voice/test_openai_streaming_speech.py`

**Interfaces:**
- Consumes: Task 1 typed config.
- Produces: exact transcription-session wire `{type: semantic_vad, eagerness, create_response: false, interrupt_response: false}` and fail-closed echo validation.

- [ ] **Step 1: Write RED wire/echo tests**

```python
request = RecognitionStreamRequest(ref, RecognitionTurnDetection.semantic_vad_configured(SemanticVadEagerness.HIGH))
await provider.open_recognition(request, timeout_seconds=1)
update = decode_sent_json(socket.sent[0])
assert update["session"]["audio"]["input"]["turn_detection"] == {
    "type": "semantic_vad",
    "eagerness": "high",
    "create_response": False,
    "interrupt_response": False,
}
```

Parameterize rejection for missing/wrong type, wrong eagerness, unknown governed key and either authority boolean true. Add a real transcription-session-shaped echo that omits false authority booleans and must pass.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit_tests/live_voice/test_openai_streaming_speech.py -q --no-cov -k 'semantic_vad'
```

- [ ] **Step 3: Implement mode-specific wire and echo normalization**

```python
if detection.mode is RecognitionTurnDetectionMode.SEMANTIC_VAD:
    config = detection.semantic_vad
    assert config is not None
    return {
        "type": "semantic_vad",
        "eagerness": config.eagerness.value,
        "create_response": False,
        "interrupt_response": False,
    }
```

For echo comparison, govern exactly `type` and `eagerness`; allow only the two optional authority booleans and require them false when present. Keep the Server VAD governed fields unchanged.

- [ ] **Step 4: Generalize private commit ownership without renaming compatibility values**

Use a private Provider-VAD owner for Server and Semantic modes. Return existing Server dispositions for Server mode and new Semantic dispositions for Semantic mode. Both must reject a client wire commit.

- [ ] **Step 5: Run GREEN and full Adapter regressions**

```bash
uv run pytest tests/unit_tests/live_voice/test_openai_streaming_speech.py -q --no-cov
uv run ruff check jiuwenswarm/server/live_voice/openai_streaming_speech.py tests/unit_tests/live_voice/test_openai_streaming_speech.py
```

- [ ] **Step 6: Commit Task 2**

```bash
git add jiuwenswarm/server/live_voice/openai_streaming_speech.py tests/unit_tests/live_voice/test_openai_streaming_speech.py
git commit -m "feat(live-voice): support OpenAI semantic VAD wire"
```

### Task 3: Preserve Gateway ordering, fencing and capability truth

**Files:**
- Modify: `jiuwenswarm/gateway/live_voice/streaming_speech_route.py`
- Test: `tests/unit_tests/gateway/test_streaming_speech_route.py`

**Interfaces:**
- Consumes: Task 1 capability/config and Task 2 Provider behavior.
- Produces: Semantic VAD recognition handles with the existing single EOT future, input fence and final collector; no product activation path.

- [ ] **Step 1: Write RED route tests**

```python
handle, fallback = await owner.begin(binding, turn_detection=RecognitionTurnDetection.semantic_vad_configured(SemanticVadEagerness.AUTO))
assert handle is not None and fallback is None
provider.publish_started(handle.ref, start_ms=100)
provider.publish_stopped(handle.ref, end_ms=700)
provider.publish_committed(handle.ref)
provider.publish_final(handle.ref, "complete text")
assert (await owner.wait_end_of_turn(handle)).provider_end_ms == 700
assert (await owner.finish(handle)).final_text == "complete text"
assert provider.client_commit_calls == 0
```

Add capability-absent fallback, stopped-before-started, duplicate stopped/commit/final, audio-after-fence, cancel-vs-final, close-vs-open and cleanup-capacity tests.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit_tests/gateway/test_streaming_speech_route.py -q --no-cov -k 'semantic_vad'
```

- [ ] **Step 3: Generalize the Provider-owned VAD checks**

```python
provider_vad = request.turn_detection.mode in {
    RecognitionTurnDetectionMode.SERVER_VAD,
    RecognitionTurnDetectionMode.SEMANTIC_VAD,
}
```

Allocate speech-start/EOT futures for either Provider-owned mode, retain the exact existing boundary validation, and require the matching explicit capability provenance. Do not change `DedicatedMediaProductRegistry.begin_streaming_recognition()`, which continues selecting `server_vad_default()` for the product.

- [ ] **Step 4: Run GREEN and affected route regressions**

```bash
uv run pytest tests/unit_tests/gateway/test_streaming_speech_route.py tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py -q --no-cov
uv run ruff check jiuwenswarm/gateway/live_voice/streaming_speech_route.py tests/unit_tests/gateway/test_streaming_speech_route.py
```

- [ ] **Step 5: Commit Task 3**

```bash
git add jiuwenswarm/gateway/live_voice/streaming_speech_route.py tests/unit_tests/gateway/test_streaming_speech_route.py
git commit -m "feat(live-voice): preserve semantic VAD route authority"
```

### Task 4: Extend the existing VAD benchmark and report

**Files:**
- Modify: `scripts/live_voice/vad_eot_causal_benchmark.py`
- Modify: `scripts/live_voice/vad_eot_benchmark_support.py`
- Test: `tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py`

**Interfaces:**
- Consumes: existing corpus loader, absolute pacing, Provider factory, integrity oracle, cleanup and mode-600 writer.
- Produces: closed configs `A1_1200`, `B_AUTO`, `A2_1200`, `B_HIGH`; report schema revision with `turn_detection_mode` and nullable `semantic_eagerness`.

- [ ] **Step 1: Write RED configuration/report tests**

```python
assert parse_configuration("B_AUTO") == VadConfiguration(
    configuration_id="B_AUTO",
    mode=RecognitionTurnDetectionMode.SEMANTIC_VAD,
    silence_duration_ms=None,
    semantic_eagerness=SemanticVadEagerness.AUTO,
)
assert parse_configuration("A1_1200").silence_duration_ms == 1200
```

Assert the existing fixed-threshold CLI remains accepted, private fields remain rejected, non-success attempts carry no numeric latency and report overwrite/mode/hash protections remain intact.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py -q --no-cov
```

- [ ] **Step 3: Generalize configuration only; reuse every existing oracle**

```python
def turn_detection_for(configuration: VadConfiguration) -> RecognitionTurnDetection:
    if configuration.mode is RecognitionTurnDetectionMode.SERVER_VAD:
        return RecognitionTurnDetection(
            RecognitionTurnDetectionMode.SERVER_VAD,
            server_vad=ServerVadConfig(silence_duration_ms=configuration.silence_duration_ms),
        )
    return RecognitionTurnDetection.semantic_vad_configured(configuration.semantic_eagerness)
```

Do not fork pacing, transcript comparison, event-order validation, forbidden counters or cleanup code. Add only the mode-specific expected commit disposition.

- [ ] **Step 4: Add the exact A/B/A commands**

Extend the existing closed parser with one optional experiment selector:

```python
parser.add_argument(
    "--experiment",
    choices=("fixed-threshold", "semantic-auto", "semantic-high"),
    default="fixed-threshold",
)
```

```text
pilot|run --experiment semantic-auto  -> A1_1200,B_AUTO,A2_1200
pilot|run --experiment semantic-high  -> A1_1200,B_HIGH,A2_1200
```

Keep the existing `--manifest`, `--output`, `--run-id` and `--git-commit`
arguments. The pilot uses one attempt per case; formal `run` uses five. The CLI
refuses mixed corpora, dirty source for credited mode, changed model labels and
reused run IDs.

- [ ] **Step 5: Run GREEN and static checks**

```bash
uv run pytest tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py -q --no-cov
uv run ruff check scripts/live_voice/vad_eot_causal_benchmark.py scripts/live_voice/vad_eot_benchmark_support.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py
uv run python -m py_compile scripts/live_voice/vad_eot_causal_benchmark.py scripts/live_voice/vad_eot_benchmark_support.py
```

- [ ] **Step 6: Commit Task 4**

```bash
git add scripts/live_voice/vad_eot_causal_benchmark.py scripts/live_voice/vad_eot_benchmark_support.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py
git commit -m "test(live-voice): extend VAD benchmark for semantic modes"
```

### Task 5: Build and verify the expanded private English semantic corpus

**Files:**
- Create: `scripts/live_voice/prepare_semantic_vad_corpus.py`
- Create: `tests/unit_tests/live_voice/test_prepare_semantic_vad_corpus.py`
- Private create: `/home/renan/openJiuwen-ai/live-voice-latency-corpus/semantic-vad-en-v1/`

**Interfaces:**
- Consumes: immutable source WAVs supplied outside Git.
- Produces: private manifest `live-voice.semantic-vad-corpus.v1` with exact hashes, audio facts, final voiced frames, expected normalized transcripts and required continuation tokens.

- [ ] **Step 1: Write RED corpus validation tests**

```python
manifest = load_semantic_corpus(tmp_path / "manifest.json")
assert {case.semantic_shape for case in manifest.cases} == {
    "complete_declarative", "direct_question", "complete_command",
    "hesitation_continuation", "trailing_conjunction", "multi_clause_pause",
    "complete_short_answer", "final_silence_control",
}
```

Reject missing/duplicate shapes, non-mono/16-bit/48-kHz WAV, unknown field, hash mismatch, final voiced frame outside bounds, absent continuation tokens and additive rather than exact declared pauses.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit_tests/live_voice/test_prepare_semantic_vad_corpus.py -q --no-cov
```

- [ ] **Step 3: Implement a deterministic create/verify CLI**

```python
parser.add_argument("--mode", choices=("create", "verify"), required=True)
parser.add_argument("--source-manifest", type=Path, required=True)
parser.add_argument("--output-dir", type=Path, required=True)
```

Use `wave`, SHA-256 and exclusive output creation. Never print transcript, raw PCM or private paths in credited JSON/log output; print only corpus ID, case count and aggregate manifest hash.

- [ ] **Step 4: Run GREEN, create and independently verify the private corpus**

```bash
uv run pytest tests/unit_tests/live_voice/test_prepare_semantic_vad_corpus.py -q --no-cov
uv run python scripts/live_voice/prepare_semantic_vad_corpus.py --mode create --source-manifest /home/renan/openJiuwen-ai/live-voice-latency-corpus/semantic-vad-en-v1-source.json --output-dir /home/renan/openJiuwen-ai/live-voice-latency-corpus/semantic-vad-en-v1
uv run python scripts/live_voice/prepare_semantic_vad_corpus.py --mode verify --source-manifest /home/renan/openJiuwen-ai/live-voice-latency-corpus/semantic-vad-en-v1-source.json --output-dir /home/renan/openJiuwen-ai/live-voice-latency-corpus/semantic-vad-en-v1
```

- [ ] **Step 5: Commit code/tests only**

```bash
git add scripts/live_voice/prepare_semantic_vad_corpus.py tests/unit_tests/live_voice/test_prepare_semantic_vad_corpus.py
git commit -m "test(live-voice): add semantic VAD corpus verifier"
```

### Task 6: Run real-Provider pilot and formal A/B/A screens

**Files:**
- Create after successful runs: `live-voice/evidence/SEMANTIC_VAD_CAUSAL_RESULT_2026-08-21.md`

**Interfaces:**
- Consumes: exact clean commit from Tasks 1--5, current Provider credentials/configuration and immutable private corpora.
- Produces: separate closed decisions for `auto` and `high`.

- [ ] **Step 1: Preflight exact source and Provider environment**

```bash
test -z "$(git status --porcelain)"
git rev-parse HEAD
test -n "$LIVE_VOICE_SPEECH_API_KEY"
uv run python scripts/live_voice/prepare_semantic_vad_corpus.py --mode verify --source-manifest /home/renan/openJiuwen-ai/live-voice-latency-corpus/semantic-vad-en-v1-source.json --output-dir /home/renan/openJiuwen-ai/live-voice-latency-corpus/semantic-vad-en-v1
```

Record only sanitized Provider/model/runtime labels; never print the key.

- [ ] **Step 2: Run one-attempt pilots on `vad-en-v1`**

```bash
uv run python scripts/live_voice/vad_eot_causal_benchmark.py pilot --experiment semantic-auto --manifest /home/renan/openJiuwen-ai/live-voice-latency-corpus/vad-en-v1/manifest.json --output /home/renan/openJiuwen-ai/live-voice-latency-runs/semantic-vad-auto-pilot/report.json --run-id semantic-vad-auto-pilot --git-commit "$(git rev-parse HEAD)"
uv run python scripts/live_voice/vad_eot_causal_benchmark.py pilot --experiment semantic-high --manifest /home/renan/openJiuwen-ai/live-voice-latency-corpus/vad-en-v1/manifest.json --output /home/renan/openJiuwen-ai/live-voice-latency-runs/semantic-vad-high-pilot/report.json --run-id semantic-vad-high-pilot --git-commit "$(git rev-parse HEAD)"
```

Stop on any Provider incompatibility, pacing-invalid, unknown or cleanup failure.

- [ ] **Step 3: Run five-attempt fast screens**

Repeat both commands with positional mode `run`, fresh run IDs and fresh output
files. Formal `run` owns five attempts per case. Require 20/20 for each B arm
before the expanded corpus.

- [ ] **Step 4: Run the expanded semantic-generalization blocks**

Run separate `auto` and `high` A/B/A blocks against `/home/renan/openJiuwen-ai/live-voice-latency-corpus/semantic-vad-en-v1`, five attempts per case and arm.

- [ ] **Step 5: Apply the closed decision rules and write sanitized evidence**

Record all per-case p50/p95 values for `final_voiced_frame_to_eot_ms`, `eot_to_final_ms` and `final_voiced_frame_to_final_ms`, outcome counts, A1/A2 drift, cleanup/pacing and zero forbidden effects. Emit exactly one decision per candidate from the spec's closed enum.

- [ ] **Step 6: Commit the evidence**

```bash
git add live-voice/evidence/SEMANTIC_VAD_CAUSAL_RESULT_2026-08-21.md
git commit -m "docs(live-voice): record semantic VAD causal result"
```

### Task 7: Complete Tier-3 review and synchronize current documentation

**Files:**
- Modify: `live-voice/evidence/SEMANTIC_VAD_CAUSAL_RESULT_2026-08-21.md`
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`
- Modify: `live-voice/STATUS.md`

- [ ] **Step 1: Run cumulative verification**

```bash
uv run pytest tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/live_voice/test_speech_ports.py tests/unit_tests/live_voice/test_openai_streaming_speech.py tests/unit_tests/gateway/test_streaming_speech_route.py tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py tests/unit_tests/live_voice/test_prepare_semantic_vad_corpus.py -q --no-cov
uv run ruff check jiuwenswarm/server/live_voice/streaming_speech.py jiuwenswarm/server/live_voice/openai_streaming_speech.py jiuwenswarm/gateway/live_voice/streaming_speech_route.py scripts/live_voice/vad_eot_causal_benchmark.py scripts/live_voice/vad_eot_benchmark_support.py scripts/live_voice/prepare_semantic_vad_corpus.py
git diff --check
```

- [ ] **Step 2: Perform independent Tier-3 module-boundary review**

Review the complete diff from the packet baseline against all P/N/B/S/T/C/R/I/F/K/X dimensions. Record findings, fixes and materially affected reruns in the result document.

- [ ] **Step 3: Synchronize only truthful current facts**

Update STATUS and the inventory with the exact eligible/rejected/incompatible/incomplete outcome. Do not claim Browser, device, multilingual, product-default or Production acceptance.

- [ ] **Step 4: Commit documentation closure**

```bash
git add live-voice/evidence/SEMANTIC_VAD_CAUSAL_RESULT_2026-08-21.md live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md live-voice/STATUS.md
git commit -m "docs(live-voice): close semantic VAD packet"
```
