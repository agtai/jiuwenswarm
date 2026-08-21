# TTS Provider Connection Reuse Implementation Plan

> **Execution result:** closed as `REJECTED` on 2026-08-21. Tasks 1–5 and the
> A1-v2/B portion of Task 6 completed. A2 was intentionally skipped after B
> proved 0/3 warm connection reuse and regressed warm first-PCM p50. Task 7
> restored request-scoped product lifecycle and synchronized documentation.
> Total real calls: 20/26 authorized. See
> [the result](TTS_PROVIDER_CONNECTION_REUSE_RESULT_2026-08-21.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure and, only if the closed A1/B/A2 gates pass, retain one
Provider-owned HTTP connection pool that reduces real OpenAI streaming-TTS time
to first PCM without changing synthesis correctness, retries or product
authority.

**Architecture:** Add a content-free HTTPCore timing observer and a closed
no-Browser benchmark around the existing Provider before changing transport
ownership. Then move the default HTTPX client from request scope into the
`OpenAIStreamingSpeechProvider` lifecycle, while each synthesis stream continues
to own only its response. Run the paid control and candidate populations on
exact clean commits, review the candidate before its paid run, and accept it
only through the spec's causal and drift gates.

**Tech Stack:** Python 3.11, asyncio, HTTPX 0.28.1, HTTPCore 1.0.9, pytest,
Ruff, Git worktrees, OpenAI-compatible streaming TTS SSE.

**Spec:**
`live-voice/roadmap/TTS_PROVIDER_CONNECTION_REUSE_SPEC_2026-08-21.md`

## Global Constraints

- Work only in the isolated branch `latency/tts-provider-connection-reuse`.
- The planning base is `1f2ac7ba4ef2ed6a4aee498d0d285a7f40a25403`;
  the exact A reference is a later clean benchmark-seam commit derived from it.
- The original experiment allowed 20 real TTS calls. The user later authorized
  six additional calls for an exact-runner A1-v2, raising the cap to 26. The
  run used 20 calls; A2's six calls were not needed after causal rejection.
- No startup probe, dummy phrase, retry, replay, fallback, Agent, Tool, Task,
  history, Browser, STT or VAD effect is allowed.
- The fixed request configuration uses one Provider, model, voice, short fixed
  English text and 24 kHz output across all populations.
- The default pool is exactly `max_connections=8`,
  `max_keepalive_connections=8`, `keepalive_expiry=30.0`,
  `follow_redirects=False`, `timeout=None`.
- Authorization, model, voice and text remain request-local; none becomes a
  client default or report field.
- Raw reports are exclusive-create, mode `0600`, outside Git, and never contain
  credentials, URLs, headers, input text, PCM, SSE payloads, exception text or
  session/user identity.
- A custom injected `sse_factory`, invalid configuration and feature-off paths
  allocate zero default HTTP clients.
- Product behavior never depends on diagnostic events. Unknown trace events and
  observer exceptions are inert.
- Risk is Tier 2. The applicable P/N/B/S/T/C/R/I/F/K/X evidence matrix and an
  independent Tier-2 review must close before the paid B population.
- Browser, audible-output, batch TTS, STT WebSocket, Agent/Task/P3, caching,
  prefetch and public SLO claims remain excluded.

## File Map

- `jiuwenswarm/server/live_voice/openai_streaming_speech.py`: owns the closed
  diagnostic event seam, default HTTPX client lifecycle and response cleanup.
- `scripts/live_voice/tts_provider_connection_causal_benchmark.py`: owns CLI,
  real-Provider pair execution, closed report validation and private write.
- `tests/unit_tests/live_voice/test_tts_provider_connection_causal_benchmark.py`:
  owns runner schema, privacy, source, pairing, trace and report tests.
- `tests/unit_tests/live_voice/test_openai_streaming_speech.py`: owns Provider
  observer, client reuse, concurrency, cancel and cleanup causality.
- `tests/unit_tests/gateway/test_streaming_synthesis_route.py`: proves Gateway
  selection/fallback authority and Provider close remain unchanged.
- `tests/unit_tests/gateway/test_product_streaming_synthesis.py`: proves exact
  ordered product synthesis behavior remains unchanged.
- `live-voice/roadmap/TTS_PROVIDER_CONNECTION_REUSE_RESULT_2026-08-21.md`:
  records sanitized A1/B/A2 evidence and the final accepted/rejected/
  inconclusive decision.
- `live-voice/STATUS.md`: receives only the final current-state fact after the
  evidence and review gates close.

---

### Task 1: Add the content-free Provider timing seam

**Files:**
- Modify: `jiuwenswarm/server/live_voice/openai_streaming_speech.py`
- Test: `tests/unit_tests/live_voice/test_openai_streaming_speech.py`

**Interfaces:**
- Consumes: `SynthesisStreamRef`, `time.monotonic`, the HTTPX request extension
  `extensions={"trace": async_callback}` and existing SSE parsing.
- Produces: `SynthesisTransportEventName`, `SynthesisTransportObserver`, and the
  optional constructor argument
  `synthesis_transport_observer: SynthesisTransportObserver | None = None`.
- Produces internal `_observe_synthesis_transport(ref, name)` behavior that is
  content-free, once-only for `first_audio_event`, exception-contained and inert
  when no observer exists.

- [ ] **Step 1: Write RED tests for the closed event union and normalization**

  Add tests that inject a fake HTTPX transport or call the internal trace
  callback through a captured request extension. Use exact names and prove
  prefix normalization without accepting arbitrary suffixes:

  ```python
  observed: list[tuple[SynthesisStreamRef, str, float]] = []
  provider = OpenAIStreamingSpeechProvider(
      config,
      synthesis_transport_observer=lambda ref, name, at: observed.append(
          (ref, name, at)
      ),
      monotonic=clock.now,
  )
  await trace("connection.connect_tcp.started", {"host": b"private"})
  await trace("connection.start_tls.complete", {"ssl_object": object()})
  await trace("http11.receive_response_body.started", {})
  assert [(ref, name) for ref, name, _ in observed] == [
      (request.ref, "connect_tcp.started"),
      (request.ref, "start_tls.complete"),
  ]
  ```

- [ ] **Step 2: Run the diagnostic tests and confirm RED**

  Run:

  ```bash
  uv run pytest tests/unit_tests/live_voice/test_openai_streaming_speech.py \
    -k 'synthesis_transport_observer or httpcore_trace or first_audio_event' -q
  ```

  Expected: collection or assertion failure because the observer interface and
  trace extension do not exist.

- [ ] **Step 3: Implement the closed observer types and safe dispatch**

  Define the closed names and callback type beside the existing speech
  transport protocols:

  ```python
  SynthesisTransportEventName = Literal[
      "connect_tcp.started",
      "connect_tcp.complete",
      "start_tls.started",
      "start_tls.complete",
      "send_request_headers.started",
      "receive_response_headers.complete",
      "first_audio_event",
  ]
  SynthesisTransportObserver = Callable[
      [SynthesisStreamRef, SynthesisTransportEventName, float], None
  ]
  ```

  Store only the optional callback. The trace adapter matches the seven exact
  suffixes, discards `info`, calls the observer with `self._monotonic()`, ignores
  its return value, and catches ordinary callback exceptions without logging
  their text. Preserve `KeyboardInterrupt`, `SystemExit` and cancellation.

- [ ] **Step 4: Wire the per-request trace callback and first audio mark**

  Pass a request-specific callback to the default HTTPX request via
  `extensions={"trace": trace_callback}`. Emit `first_audio_event` exactly once
  after a valid audio delta has decoded but before it enters the resampler. Do
  not add trace behavior to custom `sse_factory` calls and do not serialize or
  log observed facts.

- [ ] **Step 5: Add RED/GREEN fault and parity cases**

  Cover:

  ```python
  def raising_observer(*_args: object) -> None:
      raise RuntimeError("private-sentinel")

  # Synthesis still yields the same AUDIO...COMPLETED sequence.
  # Two valid audio deltas yield exactly one first_audio_event.
  # No observer yields no clock calls attributable to diagnostics.
  # A custom sse_factory receives no product trace wrapper.
  ```

  Run the focused file after each minimal implementation change.

- [ ] **Step 6: Run affected Provider regression and static checks**

  ```bash
  uv run pytest tests/unit_tests/live_voice/test_openai_streaming_speech.py -q
  uv run ruff check jiuwenswarm/server/live_voice/openai_streaming_speech.py \
    tests/unit_tests/live_voice/test_openai_streaming_speech.py
  uv run python -m py_compile \
    jiuwenswarm/server/live_voice/openai_streaming_speech.py
  git diff --check
  ```

  Expected: all pass; the observer has zero product-authority branch.

---

### Task 2: Build the closed real-Provider pair runner

**Files:**
- Create: `scripts/live_voice/tts_provider_connection_causal_benchmark.py`
- Create: `tests/unit_tests/live_voice/test_tts_provider_connection_causal_benchmark.py`
- Modify: `jiuwenswarm/server/live_voice/openai_streaming_speech.py` only if a
  Task 1 interface defect is exposed by the real Provider-shaped fake.

**Interfaces:**
- Consumes: `OpenAIStreamingSpeechProvider`,
  `SynthesisTransportObserver`, `SynthesisStreamRequest`,
  `StreamingSynthesisEvent`, `TransportCleanupSnapshot` and environment-only
  Provider configuration.
- Produces: `TtsConnectionBenchmarkConfig`, `TtsConnectionAttempt`,
  `TtsConnectionCausalReport`, `run_provider_pair`, `run_benchmark`,
  `write_private_report`, `parse_report`, and CLI `main()`.
- Produces schema
  `live-voice.tts-provider-connection-causal-report.v0` with exact closed keys
  from spec section 6.3.

- [ ] **Step 1: Write RED config and closed-schema tests**

  Create tests that require absolute non-existing output, exact clean 40-hex
  commit, `mode in {"pilot", "run"}`, safe run/source labels, exactly one pair
  in pilot and three pairs in run, and finite non-negative monotonic offsets.

  ```python
  config = runner.TtsConnectionBenchmarkConfig(
      run_id="tts-connection-pilot",
      mode="pilot",
      output_path=tmp_path / "report.json",
      git_commit="a" * 40,
      source_clean=True,
      source_label="A1",
      model="gpt-4o-mini-tts",
      voice="alloy",
      output_rate_hz=24_000,
  )
  assert config.pair_count == 1
  ```

  Adversarial constructors must reject extra keys, NaN/Inf, negative or
  non-monotonic timestamps, a completed attempt with incomplete trace, a warm
  reuse guess from missing trace, and latency metrics on a non-completed attempt.

- [ ] **Step 2: Run the new test module and confirm RED import failure**

  ```bash
  uv run pytest \
    tests/unit_tests/live_voice/test_tts_provider_connection_causal_benchmark.py \
    -q
  ```

  Expected: failure because the runner module is absent.

- [ ] **Step 3: Implement immutable config, attempt and report models**

  Use frozen slotted dataclasses and enums:

  ```python
  class TtsAttemptOutcome(StrEnum):
      COMPLETED = "completed"
      FAILED = "failed"
      INVALID = "invalid"
      UNKNOWN = "unknown"

  class TtsAttemptPosition(StrEnum):
      COLD = "cold"
      WARM = "warm"

  @dataclass(frozen=True, slots=True)
  class TtsConnectionAttempt:
      pair_index: int
      position: TtsAttemptPosition
      outcome: TtsAttemptOutcome
      reason: str | None
      connection_reused: bool | None
      request_started_ms: float
      tcp_connect_started_ms: float | None
      tcp_connect_completed_ms: float | None
      tls_started_ms: float | None
      tls_completed_ms: float | None
      response_headers_ms: float | None
      transport_open_ms: float | None
      first_audio_event_ms: float | None
      first_pcm_ms: float | None
      completed_ms: float | None
      stream_closed_ms: float | None
  ```

  The report owns exact config/version labels, attempt tuple, p50/p95 summaries,
  outcome/cleanup counts and all forbidden-effect counters fixed at zero.

- [ ] **Step 4: Write RED pair-execution tests with a real Provider-shaped fake**

  Inject a Provider factory that implements the real methods and emits exact
  observer events. Prove a pair uses one Provider, two sequential exact stream
  refs, drains AUDIO then COMPLETED, closes each stream through product APIs,
  closes Provider once, and reports cold/warm separately.

  Add negative cases for timeout, malformed ordering, trace missing, trace
  duplicate/conflict, Provider failure, incomplete cleanup, cancellation and a
  fake attempt at benchmark-owned retry. Every case must finish within a bounded
  test timeout and have exactly two or fewer real-call equivalents.

- [ ] **Step 5: Implement bounded pair execution**

  `run_provider_pair` creates one Provider, executes cold then warm only if cold
  completed, and always closes Provider in `finally`. Each operation has an
  outer hard-bounded wait, and non-cooperative cleanup is classified by the
  existing cleanup snapshot rather than hidden. The fixed text exists only as a
  local request value and is cleared before report construction.

  Reuse is classified only after a completed attempt:

  ```python
  fresh = trace.has_tcp_start and trace.has_required_tls_for_https
  reused = not trace.has_tcp_start and not trace.has_tls_start
  if position is COLD and fresh:
      connection_reused = False
  elif position is WARM and reused and provider_client_still_live:
      connection_reused = True
  else:
      outcome = TtsAttemptOutcome.INVALID
      reason = "TRACE_REUSE_UNPROVEN"
  ```

  The implementation must obtain the same-client-live fact from pair ownership,
  not infer it from absence of network events.

- [ ] **Step 6: Implement exclusive private report writing and deep reparse**

  Serialize canonical JSON to an exclusive-created temporary file with mode
  `0600`, fsync, deep-parse into the closed model, then atomically install at the
  non-existing final path without overwrite. On any failure, remove only the
  task-owned temporary file. Reparse must compare the complete semantic model,
  not only top-level keys.

- [ ] **Step 7: Write RED/GREEN CLI privacy and source-binding tests**

  Cover clean Git mismatch, dirty source, existing output, unknown arguments,
  missing model/voice/provider environment, report write failure, and sentinel
  values in argparse/provider exceptions. Captured stdout/stderr may contain
  only stable error tokens. The CLI must never print the API key, URL, text,
  headers or exception content.

- [ ] **Step 8: Run complete runner and affected Provider verification**

  ```bash
  uv run pytest \
    tests/unit_tests/live_voice/test_tts_provider_connection_causal_benchmark.py \
    tests/unit_tests/live_voice/test_openai_streaming_speech.py -q
  uv run ruff check \
    scripts/live_voice/tts_provider_connection_causal_benchmark.py \
    tests/unit_tests/live_voice/test_tts_provider_connection_causal_benchmark.py \
    jiuwenswarm/server/live_voice/openai_streaming_speech.py
  uv run python -m py_compile \
    scripts/live_voice/tts_provider_connection_causal_benchmark.py
  git diff --check
  ```

- [ ] **Step 9: Commit the exact A-reference seam**

  Inspect status and diff, exclude machine-private files, then:

  ```bash
  git add \
    jiuwenswarm/server/live_voice/openai_streaming_speech.py \
    scripts/live_voice/tts_provider_connection_causal_benchmark.py \
    tests/unit_tests/live_voice/test_openai_streaming_speech.py \
    tests/unit_tests/live_voice/test_tts_provider_connection_causal_benchmark.py
  git commit -m "test(live-voice): add TTS connection causal benchmark"
  ```

  Record this 40-character clean commit as `A_REFERENCE_COMMIT`. Do not amend it
  after any real Provider call.

---

### Task 3: Run the uncredited pilot and formal A1 control

**Files:**
- Create outside Git:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-provider-connection/tts-provider-connection-en-v1-20260821/pilot.json`
- Create outside Git:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-provider-connection/tts-provider-connection-en-v1-20260821/a1.json`
- Create: `live-voice/roadmap/TTS_PROVIDER_CONNECTION_REUSE_RESULT_2026-08-21.md`

**Interfaces:**
- Consumes: clean `A_REFERENCE_COMMIT`, environment-only Provider credentials,
  exact model/voice labels and the Task 2 CLI.
- Produces: one private two-call pilot report and one private six-call A1 report.
- Produces sanitized evidence with hashes, source/config labels, aggregate
  timings, counts and stable reasons only.

- [ ] **Step 1: Freeze the exact clean A environment**

  Verify:

  ```bash
  test -z "$(git status --porcelain)"
  test "$(git rev-parse HEAD)" = "$A_REFERENCE_COMMIT"
  uv run python -c \
    'import httpx,httpcore,sys; print(sys.version.split()[0],httpx.__version__,httpcore.__version__)'
  ```

  Store only version labels and the commit in the report. Provider key and base
  remain environment-only and are never echoed.

- [ ] **Step 2: Execute exactly one uncredited pilot pair**

  Run the runner with `--mode pilot`, exact source label `A1`, output 24 kHz and
  a new absolute output path. This consumes exactly two real TTS calls.

  Expected gate: 2/2 completed; cold and warm both show fresh TCP under the
  existing per-request client; HTTPS also shows TLS; cleanup is clean; report
  is mode `0600`; forbidden counters are zero. If any condition fails, stop the
  experiment before A1 and do not change product pooling.

- [ ] **Step 3: Deep-parse and hash the pilot report**

  Use the runner's parser, verify the file mode with `stat -c '%a'`, and compute
  SHA-256. Do not print the full raw report into chat or commit it.

- [ ] **Step 4: Execute exactly three A1 pairs**

  Run `--mode run` against the same clean A reference and exact configuration.
  This consumes six real TTS calls. Do not retry a failed attempt.

  Expected materiality gate: 6/6 completed, all six `connection_reused=false`,
  every attempt has fresh TCP and required HTTPS TLS, every Provider cleanup is
  clean, and forbidden counters are zero. Otherwise record `INCONCLUSIVE`, skip
  Tasks 4-6 and retain current product lifecycle.

- [ ] **Step 5: Write and commit sanitized A1 evidence**

  Create the result document with report SHA-256, exact source/config/version
  labels, counts, cold/warm p50/p95 for request-to-headers, request-to-first
  event, request-to-first PCM and completion, plus the materiality decision.
  Include no raw request or credential data.

  ```bash
  git add live-voice/roadmap/TTS_PROVIDER_CONNECTION_REUSE_RESULT_2026-08-21.md
  git commit -m "docs(live-voice): record TTS connection A1 baseline"
  ```

  This documentation commit is not the A product reference. A2 later runs from
  a detached clean worktree at `A_REFERENCE_COMMIT`.

---

### Task 4: Move the default HTTPX client into Provider ownership

**Files:**
- Modify: `jiuwenswarm/server/live_voice/openai_streaming_speech.py`
- Modify: `tests/unit_tests/live_voice/test_openai_streaming_speech.py`
- Modify: `tests/unit_tests/gateway/test_streaming_synthesis_route.py`
- Modify: `tests/unit_tests/gateway/test_product_streaming_synthesis.py`

**Interfaces:**
- Consumes: Task 1 observer seam and existing `_TransportCleanupOwner`.
- Produces: private `_default_sse_client_factory() -> httpx.AsyncClient`,
  Provider fields `_sse_client`, `_sse_client_lock`,
  `_get_or_create_sse_client()` and `_close_sse_client()`.
- Changes `_HttpxSseStream` to own only `httpx.Response`.
- Preserves the public Provider and Gateway speech contracts.

- [ ] **Step 1: Write the RED sequential-reuse causality test**

  Patch the default client factory with a counting fake. Open and complete two
  sequential synthesis streams on one Provider. Assert the current source
  creates two clients, then state the target:

  ```python
  assert client_factory.call_count == 1
  assert first_response.close_count == 1
  assert second_response.close_count == 1
  assert client.close_count == 0
  await provider.close()
  assert client.close_count == 1
  ```

- [ ] **Step 2: Run the reuse test and confirm RED**

  ```bash
  uv run pytest tests/unit_tests/live_voice/test_openai_streaming_speech.py \
    -k 'default_sse_client_is_reused' -q
  ```

  Expected: two clients are created or the stream closes the client early.

- [ ] **Step 3: Implement the bounded client factory and response-only stream**

  Build the client exactly as:

  ```python
  httpx.AsyncClient(
      follow_redirects=False,
      timeout=None,
      limits=httpx.Limits(
          max_connections=8,
          max_keepalive_connections=8,
          keepalive_expiry=30.0,
      ),
  )
  ```

  `_HttpxSseStream` stores only the response and `aclose()` only calls
  `response.aclose()`. The Provider builds every request with request-local
  headers and payload.

- [ ] **Step 4: Implement lazy linearized client acquisition**

  `_get_or_create_sse_client()` acquires one Provider-local lock, rejects a
  closed Provider, returns the live exact client or creates exactly one. It must
  not await network I/O while holding the lock. The default path uses this
  method; custom `sse_factory` retains its existing ownership and creates no
  default client.

- [ ] **Step 5: Write RED concurrency and isolation tests**

  Use deferred client creation and simultaneous synthesis opens to prove:

  - two concurrent streams obtain one client and distinct responses;
  - closing one response does not affect the other or client;
  - Provider A and Provider B never share a client;
  - a custom factory allocates zero default clients;
  - closing while creation is pending cannot publish a client after close;
  - an invalid or already-closed Provider cannot allocate a client.

- [ ] **Step 6: Implement client cleanup through `_TransportCleanupOwner`**

  In `_close_serialized`, fence new sessions first, close/cancel all responses
  and synthesis workers, then call:

  ```python
  complete = await self._transport_cleanup_tasks.attempt(
      kind="sse-client",
      resource=client,
      cleanup=client.aclose,
  )
  ```

  Clear `_sse_client` only if `complete is True`. A failure or timeout retains
  the same reference so an exact later `close()` retries it. A Provider whose
  close began cannot reopen. Preserve process-control exceptions.

- [ ] **Step 7: Add cleanup, cancellation and replay RED/GREEN tests**

  Cover cooperative close, close failure then exact retry, cancellation-hostile
  close bounded by the existing owner, repeated idempotent close, cancel of one
  stream with another active, broken connection followed by a caller-initiated
  new request, and zero hidden product retry. Assert ordered synthesis events
  and zero duplicate PCM/terminal events.

- [ ] **Step 8: Prove Gateway and product parity**

  Add or tighten tests that one cached selected Provider handles multiple
  synthesis streams and that route close closes it once. Preserve existing
  fallback authority: a transport failure yields the existing result and no
  new Provider-owned fallback or replay.

  Run:

  ```bash
  uv run pytest \
    tests/unit_tests/live_voice/test_openai_streaming_speech.py \
    tests/unit_tests/gateway/test_streaming_synthesis_route.py \
    tests/unit_tests/gateway/test_product_streaming_synthesis.py -q
  ```

- [ ] **Step 9: Run static and affected regression gates**

  ```bash
  uv run ruff check \
    jiuwenswarm/server/live_voice/openai_streaming_speech.py \
    tests/unit_tests/live_voice/test_openai_streaming_speech.py \
    tests/unit_tests/gateway/test_streaming_synthesis_route.py \
    tests/unit_tests/gateway/test_product_streaming_synthesis.py
  uv run python -m py_compile \
    jiuwenswarm/server/live_voice/openai_streaming_speech.py
  git diff --check
  ```

- [ ] **Step 10: Commit the candidate product change**

  ```bash
  git add \
    jiuwenswarm/server/live_voice/openai_streaming_speech.py \
    tests/unit_tests/live_voice/test_openai_streaming_speech.py \
    tests/unit_tests/gateway/test_streaming_synthesis_route.py \
    tests/unit_tests/gateway/test_product_streaming_synthesis.py
  git commit -m "perf(live-voice): reuse streaming TTS Provider connection"
  ```

  Record this clean commit as `B_CANDIDATE_COMMIT`.

---

### Task 5: Close Tier-2 code review before paid candidate calls

**Files:**
- Modify only files from Tasks 1, 2 or 4 when a proven review finding requires
  remediation.
- Create: `.superpowers/sdd/TTS_PROVIDER_CONNECTION_REUSE/task-5-report.md`
  as local review evidence; do not commit ignored/private workspace material.

**Interfaces:**
- Consumes: exact `A_REFERENCE_COMMIT`, `B_CANDIDATE_COMMIT`, spec, plan and
  root `TESTING.md` Tier-2 rules.
- Produces: independent P/N/B/S/T/C/R/I/F/K/X verdict with causal test evidence
  and no open Critical/Important finding before B.

- [ ] **Step 1: Request an independent cold review**

  The reviewer reads the exact diff from A reference to B candidate, checks the
  spec rather than implementation intent, and executes fresh affected tests.
  The review must specifically audit lock ordering, close/create races,
  response/client ownership, cleanup retry identity, process-control, no hidden
  retry, trace truth, privacy and paid-run validity.

- [ ] **Step 2: Reproduce every material finding before editing**

  For each Critical or Important finding, add one causal RED test using the real
  owning interface. Do not accept stylistic or speculative changes without a
  reproducer.

- [ ] **Step 3: Apply minimal TDD remediation and rerun all Task 4 gates**

  Keep the optimization boundary unchanged. If remediation touches benchmark
  semantics, rerun Task 2 gates as well. Commit one coherent review-fix batch:

  ```bash
  git add \
    jiuwenswarm/server/live_voice/openai_streaming_speech.py \
    scripts/live_voice/tts_provider_connection_causal_benchmark.py \
    tests/unit_tests/live_voice/test_openai_streaming_speech.py \
    tests/unit_tests/live_voice/test_tts_provider_connection_causal_benchmark.py \
    tests/unit_tests/gateway/test_streaming_synthesis_route.py \
    tests/unit_tests/gateway/test_product_streaming_synthesis.py
  git commit -m "fix(live-voice): close TTS connection reuse review"
  ```

  Replace `B_CANDIDATE_COMMIT` with the final clean reviewed commit. This occurs
  before paid B calls, so it consumes no extra Provider request.

- [ ] **Step 4: Require the pre-paid-run verdict**

  Proceed only if no Critical/Important finding remains, focused tests and
  static checks pass, the source is clean, and A1 remains bound to the unchanged
  A reference. Otherwise stop without running B or A2.

---

### Task 6: Run paid B and A2 and decide the candidate

**Files:**
- Create outside Git:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-provider-connection/tts-provider-connection-en-v1-20260821/b.json`
- Create outside Git:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-provider-connection/tts-provider-connection-en-v1-20260821/a2.json`
- Modify: `live-voice/roadmap/TTS_PROVIDER_CONNECTION_REUSE_RESULT_2026-08-21.md`

**Interfaces:**
- Consumes: reviewed clean `B_CANDIDATE_COMMIT`, unchanged clean
  `A_REFERENCE_COMMIT`, exact Task 3 configuration and runner.
- Produces: six-call B and six-call A2 private reports plus one closed decision.

- [ ] **Step 1: Run B on the exact reviewed candidate**

  Verify clean source and exact commit, then execute three pairs with the same
  Provider/model/voice/text/output/configuration as A1. This consumes exactly
  six real calls. Do not retry.

  B is structurally valid only if 6/6 complete, every cold request proves a
  fresh connection, every warm request proves reuse, all cleanup snapshots are
  clean and forbidden counters remain zero.

- [ ] **Step 2: Create a detached clean A2 worktree**

  Create a new temporary worktree outside the dirty integration path at exact
  `A_REFERENCE_COMMIT`. Verify its source is clean and its runner hash matches
  the original A runner. Reuse environment configuration only; do not copy raw
  B output into it.

- [ ] **Step 3: Run A2 on the exact unchanged A reference**

  Execute three pairs with exact A1 configuration. This consumes the final six
  authorized real calls. Remove the temporary worktree only after the report is
  deeply parsed and hashed.

- [ ] **Step 4: Compute the closed A1/B/A2 comparison**

  Calculate per-position p50/p95 for:

  ```text
  request → TCP complete
  request → TLS complete
  request → response headers
  request → transport open
  request → first Provider audio event
  request → first PCM
  request → completed
  stream close duration
  ```

  Apply the exact acceptance predicates:

  - B warm first-PCM p50 improves by at least 100 ms and 10% against A1 and A2;
  - B cold p50 and p95 regress no more than 20% against either control;
  - A1/A2 cold and warm p50 drift no more than 15%;
  - B warm gains arise before headers/first event and are not shifted later;
  - outcome, reuse, cleanup and forbidden-effect counts all match their gates.

- [ ] **Step 5: Record `ACCEPTED`, `REJECTED` or `INCONCLUSIVE`**

  Update the sanitized result document with report paths, SHA-256 values, exact
  commits/version labels, full aggregate tables, gate-by-gate boolean results,
  observed limitations and final decision. Do not commit raw reports.

  If rejected or inconclusive, revert the candidate behavior in a new ordinary
  commit while retaining benchmark seams and evidence. Do not rewrite history.
  If a rerun would be scientifically necessary, stop and request authorization
  because the 20-call budget is exhausted.

- [ ] **Step 6: Run final evidence integrity checks**

  Deep-parse all four reports (pilot, A1, B, A2), verify mode `0600`, hashes,
  source/config labels, attempt counts `2/6/6/6`, no duplicate pair/position and
  zero forbidden effects.

---

### Task 7: Synchronize current documentation and final verification

**Files:**
- Modify: `live-voice/roadmap/TTS_PROVIDER_CONNECTION_REUSE_RESULT_2026-08-21.md`
- Modify: `live-voice/STATUS.md`
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md` only if
  its current queue/result facts would otherwise become stale.
- Modify: `live-voice/README.md` only if a stable reading route must expose the
  final result.

**Interfaces:**
- Consumes: final decision, exact commits, private report hashes and Tier-2
  verdict.
- Produces: a truthful current-state route that grants only no-Chrome Provider
  evidence and preserves Browser/audible/product-readiness exclusions.

- [ ] **Step 1: Update STATUS with only the evidence-supported fact**

  State whether connection reuse was accepted, rejected or inconclusive; record
  exact measured boundary and commit; preserve all broader readiness gaps.

- [ ] **Step 2: Update the latency plan/result route**

  Record the optimization's causal result and next queue item. Do not convert a
  Provider-only first-PCM result into Browser playout, P2 ACK or end-to-end
  latency credit.

- [ ] **Step 3: Run the complete affected test gate fresh**

  ```bash
  uv run pytest \
    tests/unit_tests/live_voice/test_tts_provider_connection_causal_benchmark.py \
    tests/unit_tests/live_voice/test_openai_streaming_speech.py \
    tests/unit_tests/gateway/test_streaming_synthesis_route.py \
    tests/unit_tests/gateway/test_product_streaming_synthesis.py -q
  uv run ruff check \
    scripts/live_voice/tts_provider_connection_causal_benchmark.py \
    jiuwenswarm/server/live_voice/openai_streaming_speech.py \
    tests/unit_tests/live_voice/test_tts_provider_connection_causal_benchmark.py \
    tests/unit_tests/live_voice/test_openai_streaming_speech.py \
    tests/unit_tests/gateway/test_streaming_synthesis_route.py \
    tests/unit_tests/gateway/test_product_streaming_synthesis.py
  uv run python -m py_compile \
    scripts/live_voice/tts_provider_connection_causal_benchmark.py \
    jiuwenswarm/server/live_voice/openai_streaming_speech.py
  git diff --check
  ```

- [ ] **Step 4: Inspect final status and commit documentation**

  Verify no raw report, credential, environment file or unrelated user change is
  staged. Then:

  ```bash
  git add \
    live-voice/STATUS.md \
    live-voice/roadmap/TTS_PROVIDER_CONNECTION_REUSE_RESULT_2026-08-21.md \
    live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md \
    live-voice/README.md
  git diff --cached --check
  git commit -m "docs(live-voice): close TTS connection reuse experiment"
  ```

  Stage only documentation files that actually changed.

- [ ] **Step 5: Prepare the handoff**

  Report the exact commit chain, clean/dirty status, test outputs, A1/B/A2 table,
  final decision, 20-call accounting, raw report locations/hashes, review
  verdict, exclusions and any next optimization. Do not push: every remote-ref
  update needs separate exact approval.
