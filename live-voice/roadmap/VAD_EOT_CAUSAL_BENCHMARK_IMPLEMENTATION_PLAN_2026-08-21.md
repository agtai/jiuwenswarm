# VAD/EOT No-Browser Causal Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute a no-Browser, real-OpenAI VAD/EOT screening
benchmark for 1200/900/800/1200 ms without changing the product default.

**Architecture:** Offline code derives a closed private pause corpus from one
immutable WAV. A Python runner sends its 48 kHz PCM through the existing
`OpenAIStreamingSpeechProvider` in real time, validates exact typed turn events
and writes a content-free report. Injected Provider/clock/sleep seams close the
deterministic contract; only explicit real-Provider attempts receive VAD
screening credit.

**Tech Stack:** Python 3.11, `asyncio`, stdlib `wave`/`audioop`-free PCM
conversion, existing JiuwenSwarm streaming Speech types, pytest, Ruff and the
OpenAI Realtime transcription WebSocket already used by the product.

**Spec:**
[VAD_EOT_CAUSAL_BENCHMARK_SPEC_2026-08-21.md](VAD_EOT_CAUSAL_BENCHMARK_SPEC_2026-08-21.md)

## Global Constraints

- Exact implementation base:
  `4e5971ca035a83b55b9c894f6ca3a02e17ede1f5`; its product base is
  `465a21625bf253729f00b7c84e6cc08e9bd746a2`.
- Capability/risk: Streaming Recognition VAD/EOT, Tier 2 committed-turn
  boundary.
- No Chrome, Web UI, microphone, full backend, Gateway media socket, Agent,
  Tool, Task, P2, TTS, history or playout.
- Do not modify `streaming_speech.py`, `openai_streaming_speech.py`, Gateway
  product code or the product default `silence_duration_ms=1200`.
- Corpus and raw reports remain outside Git. Output files use exclusive create
  and mode 600.
- Real Provider calls are authorized. API keys, URLs containing credentials,
  PCM, transcripts, Provider item IDs and exception text never enter reports,
  stdout, logs or Git.
- Screening order is exactly A1 `1200` → E1 `900` → E2 `800` → A2 `1200`.
- Pilot is one attempt per four cases. Formal screening is five attempts per
  case/configuration only after a clean pilot.
- A fake Provider proves code behavior only and receives no VAD-quality or
  latency credit.

---

## Task 1: Closed private corpus support and derivation

**Files:**

- Create: `scripts/live_voice/vad_eot_benchmark_support.py`
- Create: `scripts/live_voice/prepare_vad_eot_corpus.py`
- Create: `tests/unit_tests/live_voice/test_prepare_vad_eot_corpus.py`

**Interfaces:**

- Produces:
  `VadCorpusManifest`, `VadCorpusCase`, `load_vad_corpus_manifest(path)`,
  `read_pcm16_mono_wav(path)` and `normalize_transcript(text)`.
- `prepare_vad_corpus(...) -> VadCorpusManifest` writes four WAVs and one
  closed manifest through exclusive-create operations.
- Task 2 consumes the immutable manifest/case types and WAV reader.

- [ ] **Step 1: Write RED tests for canonical manifest and WAV validation**

Create literal fixtures with a 48 kHz mono, 16-bit WAV. Tests must name the
breaks: open JSON fields, bool integers, path escape, wrong SHA-256, stereo,
wrong rate/width, missing case, duplicate case, invalid pause and output
overwrite.

```python
def test_manifest_accepts_exact_four_case_contract(tmp_path: Path) -> None:
    manifest_path = write_literal_manifest(tmp_path)
    manifest = support.load_vad_corpus_manifest(manifest_path)
    assert [case.pause_ms for case in manifest.cases] == [0, 300, 600, 1000]


@pytest.mark.parametrize("mutation", OPEN_OR_NONCANONICAL_MUTATIONS)
def test_manifest_rejects_before_wav_read(tmp_path: Path, mutation) -> None:
    manifest_path, wav_reads = write_mutated_manifest(tmp_path, mutation)
    with pytest.raises(ValueError, match="VAD_CORPUS_MANIFEST_INVALID"):
        support.load_vad_corpus_manifest(manifest_path)
    assert wav_reads() == 0
```

- [ ] **Step 2: Run the corpus tests and observe RED**

Run:

```bash
uv run pytest tests/unit_tests/live_voice/test_prepare_vad_eot_corpus.py -q --no-cov
```

Expected: import/file failure because corpus support does not exist.

- [ ] **Step 3: Implement immutable corpus types and validators**

Use frozen/slotted dataclasses and exact-key validation:

```python
@dataclass(frozen=True, slots=True)
class VadCorpusCase:
    case_id: str
    pause_ms: int
    wav_path: Path
    wav_sha256: str
    final_voiced_frame: int
    second_clause_first_frame: int
    expected_normalized_transcript: str = field(repr=False)
    required_post_pause_tokens: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class VadCorpusManifest:
    schema_version: str
    corpus_id: str
    source_sha256: str
    split_frame: int
    cases: tuple[VadCorpusCase, ...]
```

`normalize_transcript` must implement NFKC → casefold → non-letter/number to
space → collapse → trim. No regex limited to ASCII is acceptable.

- [ ] **Step 4: Write RED derivation tests**

Derive from a literal WAV whose two clauses contain nonzero samples separated
by a verified low-energy boundary and whose source already ends in 2000 ms of
silence. Assert exact inserted sample counts, unchanged prefix/suffix bytes,
preserved final silence, output hashes and refusal to overwrite.

```python
def test_derivation_inserts_only_declared_pause_and_final_silence(tmp_path: Path) -> None:
    manifest = builder.prepare_vad_corpus(request_for(tmp_path))
    for case in manifest.cases:
        samples = support.read_pcm16_mono_wav(case.wav_path).samples
        assert samples[:SPLIT] == SOURCE[:SPLIT]
        assert samples[SPLIT + case.pause_ms * 48 :] == SOURCE[SPLIT:]
```

- [ ] **Step 5: Implement the corpus builder and closed CLI**

`prepare_vad_eot_corpus.py` accepts only:

```text
--source-wav ABSOLUTE
--source-sha256 64-lower-hex
--output-root ABSOLUTE-NONEXISTENT
--corpus-id vad-en-v1
--split-frame positive-safe-int
--private-expectation-json ABSOLUTE-MODE-600
```

Validate the ±10 ms split window as low energy and ensure the second clause has
nonzero energy. Write files with `open(..., "xb")`, the manifest with
`open(..., "x", encoding="utf-8")`, and chmod private artifacts to `0o600`.
The expectation JSON has exact keys `expected_normalized_transcript` and
`required_post_pause_tokens`; reading it from a private file keeps transcript
content out of argv and process listings.
On failure, remove only files created by the current invocation inside the
newly claimed output root.

- [ ] **Step 6: Run GREEN, static checks and commit Task 1**

```bash
uv run pytest tests/unit_tests/live_voice/test_prepare_vad_eot_corpus.py -q --no-cov
uv run ruff check scripts/live_voice/vad_eot_benchmark_support.py scripts/live_voice/prepare_vad_eot_corpus.py tests/unit_tests/live_voice/test_prepare_vad_eot_corpus.py
uv run python -m py_compile scripts/live_voice/vad_eot_benchmark_support.py scripts/live_voice/prepare_vad_eot_corpus.py
git diff --check
git add scripts/live_voice/vad_eot_benchmark_support.py scripts/live_voice/prepare_vad_eot_corpus.py tests/unit_tests/live_voice/test_prepare_vad_eot_corpus.py
git commit -m "test(live-voice): add private VAD pause corpus builder"
```

---

## Task 2: Closed benchmark configuration, outcomes and report

**Files:**

- Create: `scripts/live_voice/vad_eot_causal_benchmark.py`
- Create: `tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py`

**Interfaces:**

- Consumes Task 1's `VadCorpusManifest` and `VadCorpusCase`.
- Produces frozen `VadBenchmarkConfig`, `VadAttemptResult`,
  `VadConfigurationSummary`, `VadBenchmarkReport` and
  `write_vad_benchmark_report(path, report)`.
- Task 3 implements
  `run_vad_attempt(config, case, attempt_index, *, provider_factory,
  monotonic, sleep)`.

- [ ] **Step 1: Write RED tests for exact configuration and CLI parsing**

Require absolute manifest/output paths, unique bounded run ID, exact Git SHA,
clean source, modes `pilot|run`, exact threshold sequence and sample counts
`1|5`. Reject bools, duplicates, unknown flags, newline/control characters,
relative paths and existing output before Provider/environment access.

```python
def test_cli_freezes_pilot_and_formal_sequences(tmp_path: Path) -> None:
    pilot = runner.parse_args(valid_argv(tmp_path, mode="pilot"))
    formal = runner.parse_args(valid_argv(tmp_path, mode="run"))
    assert pilot.thresholds_ms == (1200, 900, 800, 1200)
    assert pilot.attempts_per_case == 1
    assert formal.attempts_per_case == 5
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py -q --no-cov
```

Expected: module/file missing.

- [ ] **Step 3: Implement closed dataclasses and result invariants**

Use explicit enums:

```python
class VadAttemptOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class VadAttemptResult:
    configuration_id: str
    silence_duration_ms: int
    case_id: str
    attempt_index: int
    outcome: VadAttemptOutcome
    reason: str
    speech_started_count: int
    speech_stopped_count: int
    committed_count: int
    final_count: int
    exact_identity: bool
    transcript_complete: bool
    cleanup_complete: bool
    pacing_valid: bool
    final_voiced_frame_to_eot_ms: float | None
    eot_to_final_ms: float | None
    final_voiced_frame_to_final_ms: float | None
```

Construction rejects numeric latency on non-completed/invalid attempts,
completed attempts without every boolean gate, nonfinite values and private
reason text. Reasons are a closed enum such as `OK`, `EARLY_EOT`,
`TURN_COUNT_MISMATCH`, `TRANSCRIPT_INCOMPLETE`, `PACING_INVALID`,
`PROVIDER_UNAVAILABLE`, `PROVIDER_PROTOCOL`, `TIMEOUT` and
`CLEANUP_INCOMPLETE`.

- [ ] **Step 4: Write RED privacy/report tests**

Test exclusive create, mode 600, closed top/attempt/summary fields,
nearest-rank p50/p95, per-case aggregation and absence of private sentinels in
JSON/stdout/logs. A failed or invalid attempt must be counted but excluded from
latency samples.

- [ ] **Step 5: Implement report reduction and writer**

The report schema is `live-voice.vad-eot-causal-report.v0`. Summaries are keyed
by `(configuration_id, silence_duration_ms, case_id)` and retain attempts,
completed/failed/unknown/invalid counts plus p50/p95 only when every sample is
eligible. `forbidden_effects` is the exact zero-valued map from the spec.

- [ ] **Step 6: Run GREEN and commit Task 2**

```bash
uv run pytest tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py -q --no-cov
uv run ruff check scripts/live_voice/vad_eot_causal_benchmark.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py
uv run python -m py_compile scripts/live_voice/vad_eot_causal_benchmark.py
git diff --check
git add scripts/live_voice/vad_eot_causal_benchmark.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py
git commit -m "test(live-voice): add closed VAD benchmark report"
```

---

## Task 3: Deterministic paced Provider-attempt engine

**Files:**

- Modify: `scripts/live_voice/vad_eot_causal_benchmark.py`
- Modify: `tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py`

**Interfaces:**

- Produces a narrow `VadRecognitionProvider` Protocol containing only the
  recognition open/send/commit/event/cancel/close methods and a cleanup
  snapshot.
- `run_vad_attempt(config, case, attempt_index, *, provider_factory,
  monotonic, sleep) -> Awaitable[VadAttemptResult]`.
- `provider_factory(turn_detection) ->
  Awaitable[VadRecognitionProvider]` returns a fresh exact owner per attempt.
- Task 4 supplies the real OpenAI factory and Task 5 orchestrates attempts.

- [ ] **Step 1: Write RED positive pacing/event test**

Use an injected fake Provider that records frames and returns exact
`SPEECH_STARTED`, `SPEECH_STOPPED`, `COMMITTED`, `FINAL`. Use a manual clock and
sleep that advances to absolute 20 ms deadlines.

```python
@pytest.mark.asyncio
async def test_attempt_paces_contiguous_frames_and_accepts_one_exact_turn() -> None:
    result = await runner.run_vad_attempt(
        config(), corpus_case(), 0,
        provider_factory=provider_factory(events=ONE_COMPLETE_TURN),
        monotonic=clock.now,
        sleep=clock.sleep,
    )
    assert result.outcome is VadAttemptOutcome.COMPLETED
    assert provider.frame_facts == contiguous_20ms_frame_facts()
    assert result.final_voiced_frame_to_eot_ms == 1200.0
```

- [ ] **Step 2: Write RED turn-integrity and timing-failure matrix**

Separate tests for EOT before the last post-pause voiced frame, two speech
items, missing committed/final, wrong ref/item, tail transcript missing,
non-server disposition, send/event timeout, Provider exception, pacing p95
over 20 ms, pacing max over 50 ms and incomplete cleanup. Assert stable outcome
and zero latency samples for each rejection.

- [ ] **Step 3: Implement the attempt state machine**

Start the event collector before frame pacing. Store transcript only in a local
variable marked `repr=False` or ordinary local scope; normalize/compare, then
clear it before returning. Record Provider item identity only in local state.
Use `asyncio.TaskGroup` or explicit retained tasks with a single bounded
settlement path. Always `await provider.close()` in `finally` and classify
cleanup from `cleanup_snapshot`.

The sender uses:

```python
deadline = send_epoch + frame_index * 0.020
await sleep(max(0.0, deadline - monotonic()))
lateness_ms = max(0.0, (monotonic() - deadline) * 1000.0)
await provider.send_recognition_audio(frame)
```

- [ ] **Step 4: Write RED wire-authority test with real Adapter + fake socket**

Instantiate the actual `OpenAIStreamingSpeechProvider` around a fake
`RealtimeSocket`. Assert the session update carries the requested threshold,
the fake echo mismatch fails, server VAD sends zero client commit, and frames
offered after `speech_stopped` generate no append message.

- [ ] **Step 5: Implement the Provider-facing request/event mapping**

Build one `RecognitionStreamRequest` with a fresh `RecognitionStreamRef` and
`ServerVadConfig(threshold=0.5, prefix_padding_ms=300,
silence_duration_ms=config_value, create_response=False,
interrupt_response=False)`. Accept only typed current-ref boundaries and one
cursorless Provider-time final. `commit_recognition` must return
`SERVER_VAD_PENDING|SERVER_VAD_OBSERVED`.

- [ ] **Step 6: Run Task 3 regression and commit**

```bash
uv run pytest tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py tests/unit_tests/live_voice/test_openai_streaming_speech.py -q --no-cov
uv run ruff check scripts/live_voice/vad_eot_causal_benchmark.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py
uv run python -m py_compile scripts/live_voice/vad_eot_causal_benchmark.py
git diff --check
git add scripts/live_voice/vad_eot_causal_benchmark.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py
git commit -m "test(live-voice): execute paced VAD attempts"
```

---

## Task 4: Real OpenAI factory, orchestration and fail-closed CLI

**Files:**

- Modify: `scripts/live_voice/vad_eot_causal_benchmark.py`
- Modify: `tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py`

**Interfaces:**

- `create_real_streaming_provider(environ) ->
  Awaitable[OpenAIStreamingSpeechProvider]` consumes the existing four Speech
  environment names without copying secrets.
- `run_screening(config, manifest, *, provider_factory, monotonic, sleep) ->
  Awaitable[VadBenchmarkReport]` executes exact configuration order.
- `main(argv) -> int` is the production CLI boundary used by Task 5;
  `_main(argv, *, environ, provider_factory, monotonic, sleep) -> Awaitable[int]`
  is the non-exported injected test seam.

- [ ] **Step 1: Write RED real-factory selection tests**

Test feature/provider/base/key/model absence, wrong provider, invalid URL and
selector degradation. Assert zero socket allocation and no secret in
exception/repr/log/stdout. The success test injects a socket factory and
requires `SpeechRouteTier.STREAMING` with no degradation fact.

- [ ] **Step 2: Implement real Provider selection**

Call `select_environment_streaming_speech(environ=environ,
batch_available=False, socket_factory=optional_test_factory)` with a private
copy containing only the existing Speech configuration entries plus
`LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED=1`. Reject any non-streaming
selection with stable `PROVIDER_UNAVAILABLE`.

- [ ] **Step 3: Write RED orchestration/order tests**

For pilot, assert calls are exactly:

```text
A1/1200: four cases × one
E1/900:  four cases × one
E2/800:  four cases × one
A2/1200: four cases × one
```

For formal, replace one with five. Assert a Provider/network/pacing/cleanup
failure in pilot stops before the next paid attempt and produces no success
report. Formal attempts continue after a truthful turn failure so the report
can reject a threshold, but abort on infrastructure-invalid/unknown outcomes.

- [ ] **Step 4: Implement screening orchestration and interpretation**

Use unique recognition identities for every attempt. Compare A1/A2 per case.
Return exactly one decision:
`READY_FOR_SCREENING` for pilot, `LOWER_THRESHOLD_ELIGIBLE`,
`FIXED_THRESHOLD_REJECTED` or `INCONCLUSIVE` for formal. Apply the spec's 10%
control-stability and 80 ms conservative tie-break literally.

- [ ] **Step 5: Write RED CLI process/privacy tests**

Exercise `_main` with the injected fake Provider and run subprocess tests only
for pre-Provider argument/source/output failures. No fake-Provider CLI flag or
environment switch may exist. Assert clean in-process exit/written report,
dirty-source rejection, mismatched `--git-commit`, existing output, cancellation
cleanup and a private Provider sentinel absent from stderr/stdout/report.

- [ ] **Step 6: Implement `main`, signal cleanup and output settlement**

The CLI prints only:

```json
{"run_id":"...","decision":"..."}
```

It writes the report only after all active Provider resources settle and the
report validates by reparsing. Any failure prints `VAD_EOT_BENCHMARK_FAILED`
and exits nonzero without a partial report.

- [ ] **Step 7: Run Task 4 gates and commit**

```bash
uv run pytest tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py -q --no-cov
uv run ruff check scripts/live_voice/vad_eot_causal_benchmark.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py
uv run python -m py_compile scripts/live_voice/vad_eot_causal_benchmark.py
git diff --check
git add scripts/live_voice/vad_eot_causal_benchmark.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py
git commit -m "test(live-voice): add real VAD screening runner"
```

---

## Task 5: Corpus preparation, clean pilot and formal screening

**Files:**

- Private create: `/home/renan/openJiuwen-ai/live-voice-latency-corpus/vad-en-v1/`
- Private create: `/home/renan/openJiuwen-ai/live-voice-latency-runs/vad-eot/<run-id>/report.json`
- Modify after result:
  `live-voice/roadmap/VAD_EOT_CAUSAL_BENCHMARK_IMPLEMENTATION_PLAN_2026-08-21.md`
- Add after result:
  `live-voice/evidence/VAD_EOT_CAUSAL_RESULT_2026-08-21.md`

**Interfaces:**

- Consumes committed Tasks 1–4 and existing `en-v1/pcm48k` source WAV.
- Produces one sanitized exact-source pilot record and, if clean, one formal
  screening result.

- [ ] **Step 1: Select and freeze the private split boundary**

Use an energy scan only to propose a between-clause low-energy frame. Inspect
the source timing once, then pass the chosen integer explicitly to the builder.
Record source SHA-256, split frame and required post-pause tokens in the private
manifest. Do not commit them if they reveal transcript content beyond the
sanitized evidence boundary.

- [ ] **Step 2: Build and independently verify `vad-en-v1`**

Run the builder with the exact source hash. Re-run manifest loading in a fresh
process and verify all output hashes, decoded WAV facts, pause sample counts and
mode 600. Preserve the immutable source corpus.

- [ ] **Step 3: Freeze a clean runner commit**

Run all Task 1–4 tests, the 189-test Streaming/OpenAI/Gateway baseline, Ruff,
`py_compile`, diff-check and scoped self-review. Commit any review corrections,
then require `git status --porcelain --untracked-files=all` to be empty.

- [ ] **Step 4: Run one real-Provider pilot**

Load credentials into the process environment without echoing them. Execute
`pilot` with exact HEAD, private manifest and a unique output. Inspect only the
sanitized report. Stop before formal repetitions on invalid/unknown,
Provider/network/echo, pacing or cleanup failure. A truthful `FAILED` early-EOT
candidate is experiment data: complete the pilot matrix and allow formal
screening to quantify it; it is never converted into a successful sample.

- [ ] **Step 5: Run independent Tier-2 review**

Review the complete runner/corpus diff and the sanitized pilot. Remediate every
Critical/Important finding through RED/GREEN and rerun only materially affected
gates plus the pilot when its semantics changed.

- [ ] **Step 6: Run formal A1/E1/E2/A2 screening**

Use the same exact clean commit, Provider/model labels, corpus hash and machine.
Run five attempts per case/configuration. Preserve the raw mode-600 report
outside Git.

- [ ] **Step 7: Interpret without changing product source**

- `LOWER_THRESHOLD_ELIGIBLE`: record the selected threshold and create a later
  default-change spec/branch; do not change it in this packet.
- `FIXED_THRESHOLD_REJECTED`: retain 1200 ms and route a semantic/adaptive-VAD
  spec.
- `INCONCLUSIVE`: record the failed infrastructure/stability gate and no
  optimization claim.

- [ ] **Step 8: Commit sanitized evidence**

The evidence records exact commit/run IDs, corpus aggregate hash, Provider/model
labels, per-case counts/timings, decision, limitations and zero forbidden
effects. It contains no raw transcript, audio, credentials, item IDs or private
exceptions.

```bash
git add live-voice/evidence/VAD_EOT_CAUSAL_RESULT_2026-08-21.md live-voice/roadmap/VAD_EOT_CAUSAL_BENCHMARK_IMPLEMENTATION_PLAN_2026-08-21.md
git commit -m "docs(live-voice): record VAD causal screening"
```

---

## Task 6: Final verification and current documentation synchronization

**Files:**

- Modify: `live-voice/STATUS.md`
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md`
- Modify: `live-voice/roadmap/VAD_EOT_CAUSAL_BENCHMARK_IMPLEMENTATION_PLAN_2026-08-21.md`

**Interfaces:**

- Consumes Task 5's exact sanitized decision.
- Produces current status only; it grants no Browser/end-to-end/product credit.

- [ ] **Step 1: Update only the owning current facts**

STATUS records the benchmark implementation and exact screening decision in the
Speech Recognition/Interaction Intelligence/Observability rows. The latency
plan marks the no-Browser VAD screening step done and routes the next owner
according to `ELIGIBLE|REJECTED|INCONCLUSIVE`. Do not duplicate the detailed
result outside the evidence file.

- [ ] **Step 2: Run final verification on exact source**

```bash
uv run pytest tests/unit_tests/live_voice/test_prepare_vad_eot_corpus.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/live_voice/test_openai_streaming_speech.py tests/unit_tests/gateway/test_streaming_speech_route.py -q --no-cov
uv run ruff check scripts/live_voice/vad_eot_benchmark_support.py scripts/live_voice/prepare_vad_eot_corpus.py scripts/live_voice/vad_eot_causal_benchmark.py tests/unit_tests/live_voice/test_prepare_vad_eot_corpus.py tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py
uv run python -m py_compile scripts/live_voice/vad_eot_benchmark_support.py scripts/live_voice/prepare_vad_eot_corpus.py scripts/live_voice/vad_eot_causal_benchmark.py
git diff --check
```

Expected: all commands exit 0; no test claims Browser, microphone, product or
Production evidence.

- [ ] **Step 3: Verify documentation links and commit synchronization**

Confirm every changed relative link resolves, raw/private paths remain
untracked and `docs/zh/live-voice/` contains no duplicate. Then:

```bash
git add live-voice/STATUS.md live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md live-voice/roadmap/VAD_EOT_CAUSAL_BENCHMARK_IMPLEMENTATION_PLAN_2026-08-21.md
git commit -m "docs(live-voice): route after VAD causal screening"
```

## Completion Gate

- Corpus derivation is exact, private, reproducible and hash-bound.
- Fake-socket tests prove session echo, frame/order/fence, failure and privacy
  behavior without receiving VAD-quality credit.
- Real Provider pilot and screening use one exact clean source and the fixed
  A1/E1/E2/A2 order.
- Early EOT or incomplete transcript is failed, never a fast success.
- Every attempt has truthful pacing and cleanup state.
- The sanitized report contains no credentials, transcript, PCM, item ID or
  private exception.
- Independent Tier-2 review has no remaining Critical/Important finding.
- The product 1200 ms default remains unchanged in this packet.
- The final decision is exactly one of `LOWER_THRESHOLD_ELIGIBLE`,
  `FIXED_THRESHOLD_REJECTED` or `INCONCLUSIVE`.
- No Chrome, Browser, microphone, end-to-end or product-readiness credit is
  claimed.
