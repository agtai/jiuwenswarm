# Stable-Sentence Agent-to-TTS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure the real current Agent-final wait, then conditionally ship one
default-off Runtime-owned stable-sentence-to-TTS overlap candidate without
changing Agent-Core, Tool or Task truth.

**Architecture:** A pure Python stability policy consumes sequenced
`AgentEvent` fragments and produces replaceable sentence candidates. A thin
no-Chrome causal runner reuses the existing latency run/recorder/report
infrastructure and must pass a materiality gate before product wiring is
allowed. Conditional product wiring promotes one candidate at a time into the
existing Presentation ledger, transports it through P2/TTS, reconciles the
eventual final, and uses a newer response generation for any correction after
delivery became potentially audible.

**Tech Stack:** Python 3.11+, asyncio, dataclasses, pytest/pytest-asyncio,
JiuwenSwarm Live Voice v2 types, existing latency probe/report modules,
TypeScript, React, Node test runner, esbuild/Vite and the existing OpenAI
streaming TTS Adapter.

**Spec:**
[`live-voice/roadmap/STABLE_SENTENCE_AGENT_TTS_AUTHORITY_SPEC_2026-08-21.md`](STABLE_SENTENCE_AGENT_TTS_AUTHORITY_SPEC_2026-08-21.md)

> **Execution result — 2026-08-21:** The Phase A materiality-screen boundary
> completed. Task 5 produced a
> real-Provider materiality decision of `STOP` at source `81903777f8dccb40ba2cb70fbe9b28d28d86c7f5`:
> candidate→final/projected-gain p50 was 177.2 ms and relative p50 was 7.43%.
> Tasks 6–12 are therefore not authorized and were intentionally not executed.
> See the [causal result](../evidence/STABLE_SENTENCE_AGENT_TTS_CAUSAL_RESULT_2026-08-21.md).

## Global Constraints

- Planning and implementation branch:
  `latency/stable-sentence-agent-tts`, based on
  `4adc8ff0b74f4f2722733d55feba86b49c7c9ac8`.
- Do not modify Agent-Core, model selection, Agent prompts, Tool execution or
  Task mutation semantics.
- Do not create a second latency run schema, batch writer, privacy protocol,
  cross-process clock subtraction or A/B/A comparer.
- New probe points are experiment-declared and content-free. Raw prompts,
  Agent output, PCM, credentials and private environment values never enter
  committed reports.
- No product rule may branch on prompt text, fixture ID or a workload label
  such as `dialogue_no_tool`.
- At most one early stable-sentence unit is synthesizing, queued or playing for
  one response.
- `chat.final` remains semantic text/history authority. A candidate is only a
  replaceable observation until Conversation Runtime promotes it.
- A complete Presentation ACK is the only current complete-unit presented
  fact. Partial playout remains `UNKNOWN`; no duration estimate becomes a word
  or source-span cursor.
- Candidate materiality gate: p50 candidate-to-final headroom at least 500 ms,
  projected p50 first-PCM gain at least 400 ms and at least 10%, useful
  candidates in multiple trace classes, zero provider-pilot prefix mismatch,
  zero forbidden effects, and no workload-specific product rule.
- If the materiality gate returns `STOP`, Tasks 6-12 are not executed. Record
  the result and close the lane without changing product behavior.
- Backend product flag:
  `JIUWENSWARM_LIVE_VOICE_STABLE_SENTENCE_TTS_ENABLED`; frontend product flag:
  `VITE_FEATURE_LIVE_VOICE_STABLE_SENTENCE_TTS`. Both default to false.
- Controlled and provider-real results must label every value `MEASURED`,
  `CONTROLLED`, `DERIVED`, `ESTIMATED` or `UNKNOWN`.
- Provider-real work may create benchmark-only TTS bytes and Provider cost, but
  cannot attach them to product media, playout, presentation or history.
- Every rejected/stale/wrong-scope/cancelled path asserts zero forbidden Agent,
  Tool, Task, product-audio, history, store and other-scope mutation.
- Tier-3 product closure requires the complete applicable root `TESTING.md`
  matrix, independent module review and cumulative seam review. Physical
  Browser first-audible acceptance remains outside this plan.

---

## File and ownership map

| File | Responsibility |
|---|---|
| `jiuwenswarm/server/live_voice/stable_sentence_policy.py` | Pure response-local accumulation, candidate selection, commitment and exact final reconciliation |
| `tests/fixtures/live_voice/stable_sentence_policy_v1.json` | Public deterministic boundary/rewrite/barrier fixtures shared by policy and runner tests |
| `tests/unit_tests/live_voice/test_stable_sentence_policy.py` | Pure policy positive, negative, boundary, state, ordering and identity oracle |
| `scripts/live_voice/stable_sentence_causal_benchmark.py` | Controlled/provider-real no-Chrome screen, standard latency artifacts, materiality reducer and A1/B/A2 driver |
| `tests/unit_tests/live_voice/test_stable_sentence_causal_benchmark.py` | Runner config, timing, privacy, gate, watchdog and comparison oracle |
| `jiuwenswarm/server/live_voice/latency_probe.py` | Permit response-bound experiment points without widening fixed core marks |
| `jiuwenswarm/server/live_voice/latency_probe_report.py` | Validate sentence experiment identity and derive declared same-clock segments |
| `tests/unit_tests/live_voice/test_latency_probe.py` | Probe point/identity/failure isolation regressions |
| `tests/unit_tests/live_voice/test_latency_probe_report.py` | Sentence experiment segment/report and incompatible-clock rejection |
| `jiuwenswarm/server/live_voice/agent_conversation_runtime.py` | Conditional candidate promotion, AUDIO units, final partitioning/reconciliation, correction generation and probe marks |
| `tests/unit_tests/live_voice/test_agent_conversation_runtime.py` | Runtime authority, cancellation, retry, history and zero-effect scenarios |
| `jiuwenswarm/server/live_voice/product_composition_registry.py` | Backend flag propagation and bounded P2 notification serialization |
| `tests/unit_tests/live_voice/test_product_composition_registry.py` | Environment flag, serialized purpose/text, notification ordering and feature-off tests |
| `jiuwenswarm/server/live_voice/formal_history_writer.py` | Coalesce one final contiguous TEXT cursor into one semantic assistant record |
| `tests/unit_tests/live_voice/test_formal_history_writer.py` | New multi-unit final coalescence, replay and content-binding tests |
| `jiuwenswarm/channels/web/frontend/src/featureFlags.ts` | Default-off frontend candidate flag |
| `jiuwenswarm/channels/web/frontend/src/vite-env.d.ts` | Typed Vite flag declaration |
| `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx` | Distinguish early AUDIO, semantic final and correction; serialize play/ACK without premature history |
| `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts` | Exact-unit TTS/playout cancellation and response-generation fence |
| `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs` | Pure notification classifier and flag-off tests |
| `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs` | Mounted early-speech/final/correction/ACK lifecycle tests |
| `jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs` | TTS/downlink late-chunk, stop and replacement tests |
| `live-voice/evidence/STABLE_SENTENCE_AGENT_TTS_CAUSAL_RESULT_2026-08-21.md` | Sanitized materiality result bound to exact source |
| `live-voice/evidence/STABLE_SENTENCE_AGENT_TTS_A_B_A_RESULT_2026-08-21.md` | Conditional accepted/rejected A1/B/A2 evidence |

## Phase A — policy and causal screen

### Task 1: Implement the Pure Stable-Sentence Policy

**Execution:** COMPLETE — commit `5541a9558c9076329d03367a41ccbefe3d219138`.

**Files:**
- Create: `jiuwenswarm/server/live_voice/stable_sentence_policy.py`
- Create: `tests/fixtures/live_voice/stable_sentence_policy_v1.json`
- Create: `tests/unit_tests/live_voice/test_stable_sentence_policy.py`

**Interfaces:**
- Consumes: `ResponseRef` and sequenced `AgentEvent` from
  `jiuwenswarm.server.live_voice.agent_bridge`.
- Produces:
  `StableSentenceStreamState`, `StableSentenceCandidate`,
  `StableSentenceObservation`, `StableSentenceCommit`,
  `StableSentenceReconciliation`, `observe_agent_event`,
  `commit_candidate`, `candidate_content`, and `reconcile_final`.

- [ ] **Step 1: Add public deterministic fixtures**

Create a JSON array whose exact cases include `append_only_english`,
`append_only_chinese`, `decimal`, `abbreviation`, `closed_code_fence`,
`unclosed_code_fence`, `rewrite_before_commit`, `tool_barrier`,
`duplicate_event`, `event_gap`, `stale_generation`, `prefix_match` and
`prefix_mismatch`. Each case declares ordered fragments, expected candidate
UTF-8 spans and final disposition; it contains no private runtime output.

- [ ] **Step 2: Write failing construction and sequence tests**

```python
state = StableSentenceStreamState.create(ResponseRef("i-1", "r-1", 0))
first = observe_agent_event(state, event(0, "chat.delta", "Paris is the capital. "))
second = observe_agent_event(first.state, event(1, "chat.delta", "It is in France"))
assert first.candidate is None
assert second.candidate is not None
assert candidate_content(second.state, second.candidate) == b"Paris is the capital. "
```

Also assert that an event gap, duplicate with changed content, wrong response,
invalid UTF-8 scalar, control character and byte-limit overflow raise stable
reason IDs before state changes.

- [ ] **Step 3: Run the focused test and verify RED**

Run:

```bash
uv run pytest -q tests/unit_tests/live_voice/test_stable_sentence_policy.py
```

Expected: collection/import failure because the policy module does not exist.

- [ ] **Step 4: Implement the immutable types and observation function**

Use these signatures:

```python
POLICY_ID = "conservative-lookahead-v1"

@dataclass(frozen=True, slots=True)
class StableSentenceStreamState:
    response_ref: ResponseRef
    observed_text: str
    committed_utf8_end: int
    next_agent_event_seq: int
    next_candidate_seq: int
    active_candidate: StableSentenceCandidate | None
    barrier_event_seq: int | None
    terminal: bool

    @classmethod
    def create(cls, response_ref: ResponseRef) -> "StableSentenceStreamState":
        return cls(response_ref, "", 0, 0, 0, None, None, False)

@dataclass(frozen=True, slots=True)
class StableSentenceCandidate:
    response_ref: ResponseRef
    candidate_id: str
    candidate_seq: int
    source_start_utf8: int
    source_end_utf8: int
    content_ref: str
    first_agent_event_seq: int
    last_agent_event_seq: int
    stability_policy_id: str
    stability_evidence: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class StableSentenceObservation:
    state: StableSentenceStreamState
    candidate: StableSentenceCandidate | None
    discarded_candidate_ids: tuple[str, ...]
    barrier: str | None

@dataclass(frozen=True, slots=True)
class StableSentenceCommit:
    state: StableSentenceStreamState
    candidate: StableSentenceCandidate

class FinalReconciliationDisposition(StrEnum):
    EXACT_PREFIX = "exact_prefix"
    REWRITE_BEFORE_COMMIT = "rewrite_before_commit"
    REWRITE_AFTER_COMMIT = "rewrite_after_commit"
    EXACT_REPLAY = "exact_replay"

@dataclass(frozen=True, slots=True)
class StableSentenceReconciliation:
    state: StableSentenceStreamState
    disposition: FinalReconciliationDisposition
    final_tail_utf8: bytes
    correction_required: bool

def observe_agent_event(
    state: StableSentenceStreamState,
    event: AgentEvent,
) -> StableSentenceObservation:
    validated = _validate_next_event(state, event)
    return _observe_validated_event(state, validated)

def candidate_content(
    state: StableSentenceStreamState,
    candidate: StableSentenceCandidate,
) -> bytes:
    encoded = state.observed_text.encode("utf-8")
    return encoded[candidate.source_start_utf8:candidate.source_end_utf8]
```

The initial boundary algorithm ports the conservative lookahead, decimal and
code-fence behavior from `liveVoiceStreamingSpeech.ts`, but operates on raw
source text. Sanitization remains outside authority.

- [ ] **Step 5: Add commit and exact-final reconciliation tests**

```python
committed = commit_candidate(observed.state, observed.candidate.candidate_id)
matched = reconcile_final(committed.state, "Paris is the capital. It is in France.")
assert matched.disposition is FinalReconciliationDisposition.EXACT_PREFIX
assert matched.final_tail_utf8 == b"It is in France."
```

Cover candidate replacement, barrier discard, exact duplicate final,
prefix-mismatch before/after commitment, and no fuzzy punctuation equality.

- [ ] **Step 6: Implement commit/reconcile minimally and run GREEN**

Run:

```bash
uv run pytest -q tests/unit_tests/live_voice/test_stable_sentence_policy.py
uv run ruff check jiuwenswarm/server/live_voice/stable_sentence_policy.py tests/unit_tests/live_voice/test_stable_sentence_policy.py
```

Expected: all focused tests pass and Ruff exits 0.

- [ ] **Step 7: Commit the pure policy**

```bash
git add jiuwenswarm/server/live_voice/stable_sentence_policy.py \
  tests/fixtures/live_voice/stable_sentence_policy_v1.json \
  tests/unit_tests/live_voice/test_stable_sentence_policy.py
git commit -m "feat(live-voice): add stable sentence policy"
```

### Task 2: Extend the Existing Probe for Sentence Experiment Points

**Execution:** COMPLETE — commit `1dbdea469b1b03bfc34eb5e6dd9f3176816d1bcc`.

**Files:**
- Modify: `jiuwenswarm/server/live_voice/latency_probe.py`
- Modify: `jiuwenswarm/server/live_voice/latency_probe_report.py`
- Modify: `tests/unit_tests/live_voice/test_latency_probe.py`
- Modify: `tests/unit_tests/live_voice/test_latency_probe_report.py`

**Interfaces:**
- Consumes: existing `LatencyExperiment.declared_experiment_points` and
  `AgentForegroundLatencyProbeOperation.mark`.
- Produces: response-bound validation and derived same-clock experiment
  segments for the five `agent.sentence_*` marks; no new run schema.

- [ ] **Step 1: Write failing probe identity tests**

Declare these experiment points in a v1 `run.json` fixture:

```python
SENTENCE_POINTS = (
    "agent.sentence_candidate_detected",
    "agent.sentence_presentation_committed",
    "agent.sentence_candidate_discarded",
    "agent.sentence_final_reconciled",
    "agent.sentence_correction_started",
)
```

Assert every sentence point requires `response_id` and
`response_generation`, rejects cross-response shards, and remains unavailable
when not declared by the experiment.

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
uv run pytest -q \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py
```

Expected: the new response-binding assertion fails for experiment points.

- [ ] **Step 3: Generalize response-bound experiment validation**

In `latency_probe_report.py`, derive response-required points from every
`agent_server` declared experiment point in addition to fixed response points:

```python
response_required_points |= {
    point.point
    for point in run.experiment.declared_experiment_points
    if point.component == "agent_server"
}
```

Keep `LatencyProbeRecorder.mark` best-effort and content-free. Do not add the
sentence names to `CORE_POINTS_BY_COMPONENT`; the experiment must declare them.

- [ ] **Step 4: Add declared segment tests**

Define and verify same-clock segments:

```text
candidate_to_final:
  agent.sentence_candidate_detected -> agent.agent_final
candidate_to_commit:
  agent.sentence_candidate_detected -> agent.sentence_presentation_committed
commit_to_reconcile:
  agent.sentence_presentation_committed -> agent.sentence_final_reconciled
```

Assert attempts with a missing mark are `unknown`, not zero, and Agent/Gateway
points cannot be paired into one segment.

- [ ] **Step 5: Run GREEN and commit**

```bash
uv run pytest -q \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py
git add jiuwenswarm/server/live_voice/latency_probe.py \
  jiuwenswarm/server/live_voice/latency_probe_report.py \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py
git commit -m "test(live-voice): bind stable sentence probe points"
```

### Task 3: Build the Controlled Causal Runner

**Execution:** COMPLETE — commit `4bb3d236c828d8174e2e2a7321938bc12c88ffb9`.

**Files:**
- Create: `scripts/live_voice/stable_sentence_causal_benchmark.py`
- Create: `tests/unit_tests/live_voice/test_stable_sentence_causal_benchmark.py`

**Interfaces:**
- Consumes: Task 1 policy, `LatencyRunConfig`, `LatencyProbeRuntime`,
  `LatencyProbeBatchWriter`, `reduce_latency_run` and
  `write_latency_report`.
- Produces: `StableSentenceAttempt`, `StableSentenceScreenSummary`,
  `run_controlled_attempt`, `reduce_materiality_gate`, and CLI commands
  `prepare`, `controlled-run`, `provider-run`, `compare`.

- [ ] **Step 1: Write failing closed-config tests**

Use the exact config:

```python
@dataclass(frozen=True, slots=True)
class StableSentenceBenchmarkConfig:
    run_json: Path
    output_path: Path
    mode: Literal["controlled", "provider-pilot", "run"]
    population: Literal["SCREEN", "A1", "B", "A2"]
    git_commit: str
    source_clean: bool

@dataclass(frozen=True, slots=True)
class TimedAgentEvent:
    observed_ms: float
    event: AgentEvent

@dataclass(frozen=True, slots=True)
class StableSentenceAttempt:
    population: str
    case_id: str
    attempt_index: int
    outcome: str
    reason: str | None
    agent_started_ms: float | None
    first_delta_ms: float | None
    candidate_detected_ms: float | None
    final_ms: float | None
    first_pcm_ms: float | None
    candidate_count: int
    discard_count: int
    prefix_match_count: int
    prefix_mismatch_count: int
    correction_count: int
    forbidden_effects: tuple[tuple[str, int], ...]
```

Assert absolute non-existing output, exact 40-character commit, clean source,
allowed population/mode combinations, bounded attempt count and existing
standard `run.json`. Invalid config exits before clock, Provider or file writes.

- [ ] **Step 2: Write failing attempt-integrity tests**

`StableSentenceAttempt` must contain only IDs, offsets, counts, outcomes and
forbidden-effect counters. A completed attempt requires monotonic:

```text
agent_started <= first_delta <= candidate_detected <= final
candidate_detected <= projected_tts_request <= projected_first_pcm
```

Failed/unknown attempts carry no latency samples. Text and PCM fields are not
part of the dataclass or serialized result.

- [ ] **Step 3: Run the runner tests and verify RED**

```bash
uv run pytest -q tests/unit_tests/live_voice/test_stable_sentence_causal_benchmark.py
```

Expected: import failure for the new runner.

- [ ] **Step 4: Implement controlled event and timing ports**

```python
class ControlledTtsPort(Protocol):
    async def first_pcm_ms(self, text_utf8: bytes) -> float:
        pass

async def run_controlled_attempt(
    config: StableSentenceBenchmarkConfig,
    events: Sequence[TimedAgentEvent],
    *,
    tts: ControlledTtsPort,
    monotonic_ms: Callable[[], float],
) -> StableSentenceAttempt:
    return await _execute_controlled_trace(config, events, tts, monotonic_ms)
```

Feed the public Task 1 fixtures through the real policy. SCREEN computes the
counterfactual candidate path without creating a PresentationUnit. A1/A2 use
the observed final gate; B is rejected in controlled mode until the product
candidate exists.

- [ ] **Step 5: Implement standard latency artifact writing**

Create an `agent_server/agent_foreground` recorder from the loaded existing
run config, submit its ordinary batch through `LatencyProbeBatchWriter`, then
run the existing report builder. The causal summary references standard batch
IDs and stores counters; it never embeds a second copy of marks.

- [ ] **Step 6: Add privacy, watchdog and atomic-write tests**

Assert output uses exclusive creation, maximum 1 MiB, mode `0600`, no report
overwrite, no prompt/output/PCM/API-key field, bounded subprocess watchdog and
zero partial success when the writer or reducer fails.

- [ ] **Step 7: Run GREEN and commit**

```bash
uv run pytest -q \
  tests/unit_tests/live_voice/test_stable_sentence_policy.py \
  tests/unit_tests/live_voice/test_stable_sentence_causal_benchmark.py \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py
git add scripts/live_voice/stable_sentence_causal_benchmark.py \
  tests/unit_tests/live_voice/test_stable_sentence_causal_benchmark.py
git commit -m "feat(live-voice): add stable sentence causal screen"
```

### Task 4: Add the Provider-Real No-Chrome Driver

**Execution:** COMPLETE for the Task 5 screen — commits
`8a125a36fd1d2023e9af938d11d57cd4f1028994` and
`81903777f8dccb40ba2cb70fbe9b28d28d86c7f5`. The conditional
`ProductRuntimeAttemptDriver`/A1-B-A2 product port was not instantiated after
the materiality `STOP`; the real formal-Agent and benchmark-only TTS ports used
by the screen are complete.

**Files:**
- Modify: `scripts/live_voice/stable_sentence_causal_benchmark.py`
- Modify: `tests/unit_tests/live_voice/test_stable_sentence_causal_benchmark.py`
- Create: `tests/fixtures/live_voice/stable_sentence_provider_cases.json`

**Interfaces:**
- Consumes: the real `AgentManager`/formal Agent facade, public fixed prompts,
  the current OpenAI streaming TTS Adapter and Task 3 result contract.
- Produces: `FormalAgentStreamClient`, `BenchmarkTtsClient` and
  `ProductRuntimeAttemptDriver` and `run_provider_attempt`.

- [ ] **Step 1: Add public provider cases and failing parser tests**

Each case contains only `case_id`, public fixed prompt, expected minimum
sentence count and `allow_tools=false`. Require at least three structurally
different cases; the product policy never sees `case_id`.

- [ ] **Step 2: Define the injected real-driver ports**

```python
class FormalAgentStreamClient(Protocol):
    async def stream(
        self, case: ProviderCase
    ) -> AsyncIterator[TimedAgentEvent]:
        pass

class BenchmarkTtsClient(Protocol):
    async def measure_first_pcm(
        self, *, response_ref: ResponseRef, unit_id: str, text_utf8: bytes
    ) -> BenchmarkTtsTiming:
        pass

@dataclass(frozen=True, slots=True)
class ProviderCase:
    case_id: str
    prompt: str
    minimum_sentence_count: int
    allow_tools: bool

@dataclass(frozen=True, slots=True)
class BenchmarkTtsTiming:
    request_started_ms: float
    transport_open_ms: float
    first_provider_audio_ms: float
    first_pcm_ms: float
    completed_ms: float
    cleanup_complete: bool

class ProductRuntimeAttemptDriver(Protocol):
    async def run(
        self,
        *,
        population: str,
        case: ProviderCase,
        tts: BenchmarkTtsClient,
    ) -> StableSentenceAttempt:
        pass
```

Tests inject fakes; the CLI factory obtains an `agent`-mode facade from the
existing `AgentManager` for one disposable project and calls
`process_formal_live_voice_stream` with an isolated `FormalAgentExecution`
whose `allow_tools` is false. It never activates product composition, sends a
presentation ACK/barge-in, enables memory or dispatches a Tool/Task command.

- [ ] **Step 3: Verify RED for connection and effect fences**

Assert response/request mismatch, unexpected Tool event,
missing final, multiple final, prefix mismatch, timeout and cleanup failure
produce failed/unknown attempts with no latency credit and no TTS call after
failure.

- [ ] **Step 4: Implement the isolated real Agent facade owner**

Create the real execution with the existing formal types:

```python
execution = FormalAgentExecution(
    request_id="stable-screen-agent-01",
    channel_id="live_voice_latency_screen",
    internal_session_id="lv-stable-screen-01",
    commit=fixed_public_turn_commit,
    context=empty_formal_context,
    allow_tools=False,
)
```

Validate every returned `AgentResponseChunk` identity and contiguous event
sequence. Accumulate output in memory only, feed mapped `AgentEvent` objects to
Task 1 policy, retain hashes/counts in the report, and release the Agent facade
and manager-owned session in `finally` under a hard timeout.

The neutral runner also constructs `AgentConversationRuntime` for A1/A2
without a candidate keyword. For B only, it supplies
`stable_sentence_tts_enabled=True`; running B on reference source therefore
fails closed, while the same unchanged runner source activates the later
candidate implementation. The runner consumes real Runtime notifications,
passes presentation text to the benchmark-only TTS client and returns exact
in-process ACKs without opening Browser media.

- [ ] **Step 5: Implement benchmark-only real TTS measurement**

Reuse `OpenAIStreamingSpeechProvider` and the event loop from
`tts_provider_connection_causal_benchmark.py`. Measure request start,
transport open, first Provider audio, first PCM, completion and cleanup. Never
open a dedicated product media route or persist PCM.

- [ ] **Step 6: Run fake-driver GREEN and commit**

```bash
uv run pytest -q tests/unit_tests/live_voice/test_stable_sentence_causal_benchmark.py
uv run ruff check scripts/live_voice/stable_sentence_causal_benchmark.py \
  tests/unit_tests/live_voice/test_stable_sentence_causal_benchmark.py
git add scripts/live_voice/stable_sentence_causal_benchmark.py \
  tests/unit_tests/live_voice/test_stable_sentence_causal_benchmark.py \
  tests/fixtures/live_voice/stable_sentence_provider_cases.json
git commit -m "feat(live-voice): add real stable sentence screen driver"
```

### Task 5: Execute and Freeze the Materiality Screen

**Execution:** COMPLETE with decision `STOP`. Step 6 is not applicable because
it is explicitly conditional on `PASS`; no local A reference was created.

**Files:**
- Create: `live-voice/evidence/STABLE_SENTENCE_AGENT_TTS_CAUSAL_RESULT_2026-08-21.md`
- Modify only if the evidence changes current analytical ordering:
  `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`

**Interfaces:**
- Consumes: exact clean Task 4 commit, running backend configuration and private
  output root.
- Produces: immutable private raw artifacts plus one sanitized `PASS` or `STOP`
  decision.

- [ ] **Step 1: Verify clean source and prepare isolated output**

```bash
git status --short --branch
git rev-parse HEAD
install -d -m 700 /home/renan/openJiuwen-ai/live-voice-latency-runs/stable-sentence-screen-20260821
```

Abort on any product-code dirtiness. Record exact Agent-Core commit,
JiuwenSwarm commit, Provider/model/voice, runtime class and network profile
without credentials.

- [ ] **Step 2: Run the controlled screen**

```bash
uv run python scripts/live_voice/stable_sentence_causal_benchmark.py prepare \
  --mode controlled \
  --population SCREEN \
  --output /home/renan/openJiuwen-ai/live-voice-latency-runs/stable-sentence-screen-20260821/controlled/run.json
uv run python scripts/live_voice/stable_sentence_causal_benchmark.py controlled-run \
  --run-json /home/renan/openJiuwen-ai/live-voice-latency-runs/stable-sentence-screen-20260821/controlled/run.json \
  --fixture tests/fixtures/live_voice/stable_sentence_policy_v1.json \
  --output /home/renan/openJiuwen-ai/live-voice-latency-runs/stable-sentence-screen-20260821/controlled/result.json
```

Require all deterministic cases to close with zero forbidden effects.

- [ ] **Step 3: Run the provider-real pilot**

```bash
export JIUWENSWARM_LATENCY_PROJECT_DIR=${JIUWENSWARM_LATENCY_PROJECT_DIR:-/home/renan/openJiuwen-ai/live-voice-latency-fixture}
test -d "$JIUWENSWARM_LATENCY_PROJECT_DIR"
test "$(git -C "$JIUWENSWARM_LATENCY_PROJECT_DIR" rev-parse --is-inside-work-tree)" = true
test -z "$(git -C "$JIUWENSWARM_LATENCY_PROJECT_DIR" remote 2>/dev/null)"
uv run python scripts/live_voice/stable_sentence_causal_benchmark.py provider-run \
  --mode provider-pilot \
  --population SCREEN \
  --project-dir "$(realpath "$JIUWENSWARM_LATENCY_PROJECT_DIR")" \
  --cases tests/fixtures/live_voice/stable_sentence_provider_cases.json \
  --output /home/renan/openJiuwen-ai/live-voice-latency-runs/stable-sentence-screen-20260821/provider-pilot/result.json
```

The project path is a machine-private input and must identify a disposable,
no-remote fixture. Record only its sanitized profile/hash, never the path or
contents, in committed evidence.

- [ ] **Step 4: Reduce the gate mechanically**

```bash
uv run python scripts/live_voice/stable_sentence_causal_benchmark.py compare \
  --screen /home/renan/openJiuwen-ai/live-voice-latency-runs/stable-sentence-screen-20260821/provider-pilot/result.json \
  --output /home/renan/openJiuwen-ai/live-voice-latency-runs/stable-sentence-screen-20260821/materiality.json
```

The reducer emits exactly `PASS` or `STOP` plus each threshold observation.

- [ ] **Step 5: Write sanitized evidence and commit**

The evidence table reports absolute p50/p95 values, sample/failure counts,
prefix-match count, candidate eligibility, projected first-PCM gain and all
truth labels. If `STOP`, explicitly state that Tasks 6-12 are not authorized.

```bash
git add live-voice/evidence/STABLE_SENTENCE_AGENT_TTS_CAUSAL_RESULT_2026-08-21.md \
  live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md
git commit -m "docs(live-voice): record stable sentence causal screen"
```

- [ ] **Step 6: Freeze the passing screen source as local A reference**

Execute only for a `PASS` gate:

```bash
git branch latency/stable-sentence-agent-tts-screen-reference HEAD
git show --no-patch --format='%H %s' latency/stable-sentence-agent-tts-screen-reference
```

This local branch is immutable input for Task 11. It does not authorize a
remote ref update.

## Phase B — conditional single product candidate

Tasks 6-12 execute only when Task 5 records `PASS` on exact clean source.

**Execution:** NOT AUTHORIZED — Task 5 recorded `STOP`. All Phase B checkboxes
remain intentionally open as non-executed conditional work, not unfinished
work in this lane.

### Task 6: Add the Default-Off Backend Runtime Candidate

**Files:**
- Modify: `jiuwenswarm/server/live_voice/product_composition_registry.py`
- Modify: `jiuwenswarm/server/live_voice/agent_conversation_runtime.py`
- Modify: `tests/unit_tests/live_voice/test_product_composition_registry.py`
- Modify: `tests/unit_tests/live_voice/test_agent_conversation_runtime.py`

**Interfaces:**
- Consumes: Task 1 policy and passing Task 5 gate.
- Produces: `stable_sentence_tts_enabled` setting, response-local policy state,
  AUDIO presentation notifications and content-free sentence probe marks.

- [ ] **Step 1: Write failing backend flag tests**

Assert `ProductCompositionSettings.from_environment()` reads only exact truthy
values for `JIUWENSWARM_LIVE_VOICE_STABLE_SENTENCE_TTS_ENABLED`, default false,
and passes the boolean to `_create_p2_runtime`. Feature-off must produce the
existing notification sequence byte-for-byte.

- [ ] **Step 2: Add failing Runtime early-unit tests**

Use a fake facade that yields:

```text
chat.delta "Paris is the capital. "
chat.delta "It is in France"
chat.final "Paris is the capital. It is in France."
```

Assert the first candidate becomes one
`PresentationUnit(surface=AUDIO, seq=0, span=0..capital_sentence_end)` before
the final notification; its notification carries exact candidate content and
does not write history.

- [ ] **Step 3: Verify RED**

```bash
uv run pytest -q \
  tests/unit_tests/live_voice/test_product_composition_registry.py \
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py \
  -k stable_sentence
```

- [ ] **Step 4: Implement settings and Runtime state**

Extend `_ResponseOutputState` with one
`StableSentenceStreamState | None` and exact delivered/ACKed early-unit sets.
Extend `AgentConversationNotification` with:

```python
presentation_text: str | None = None
presentation_purpose: str | None = None
correction_of: ResponseRef | None = None
```

Closed purposes are `stable_sentence`, `semantic_final` and `correction`.
Unknown combinations fail construction/serialization tests.

- [ ] **Step 5: Promote exactly one candidate at a time**

On `chat.delta`, call `observe_agent_event`. If eligible and no early unit is
outstanding, commit the candidate, produce/enqueue one AUDIO unit, retain its
bytes under `unit_id`, publish it as a critical presentation notification, and
mark:

```text
agent.sentence_candidate_detected
agent.sentence_presentation_committed
```

Do not transition response terminal, write history, mark final or call TTS in
the Runtime.

- [ ] **Step 6: Run GREEN and commit**

```bash
uv run pytest -q \
  tests/unit_tests/live_voice/test_product_composition_registry.py \
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py \
  -k 'stable_sentence or environment or latency_probe'
git add jiuwenswarm/server/live_voice/product_composition_registry.py \
  jiuwenswarm/server/live_voice/agent_conversation_runtime.py \
  tests/unit_tests/live_voice/test_product_composition_registry.py \
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py
git commit -m "feat(live-voice): promote stable sentence audio units"
```

### Task 7: Implement Exact Final Partitioning and Semantic History

**Files:**
- Modify: `jiuwenswarm/server/live_voice/agent_conversation_runtime.py`
- Modify: `jiuwenswarm/server/live_voice/formal_history_writer.py`
- Modify: `tests/unit_tests/live_voice/test_agent_conversation_runtime.py`
- Create: `tests/unit_tests/live_voice/test_formal_history_writer.py`

**Interfaces:**
- Consumes: Task 6 AUDIO prefix units and `chat.final`.
- Produces: aligned TEXT units, one final TEXT cursor notification, exact
  unspoken TTS tail and one coalesced semantic history record.

- [ ] **Step 1: Write failing exact-prefix partition tests**

For two early AUDIO spans plus a final tail, assert Runtime internally creates
TEXT units with the exact same prefix sequence/span/content-ref partition and
one contiguous tail TEXT unit. It publishes only the last TEXT cursor with:

```text
agent_event.text       = complete chat.final
presentation_text      = unspoken final tail
presentation_purpose   = semantic_final
presentation_unit.seq  = last TEXT cursor
```

An empty tail is legal and must not cause a TTS call downstream.

- [ ] **Step 2: Write failing history coalescence tests**

```python
written = await writer.persist_assistant(
    intent_with_contiguous_contents(b"Paris. ", b"France."),
    session_id="s-1",
    channel_id="web",
)
assert written == (True,)
assert stored_records[0]["content"] == "Paris. France."
```

Reject gaps, overlaps, digest mismatch, non-UTF-8 content, response mismatch
and replay with changed bytes before any history write.

- [ ] **Step 3: Run RED**

```bash
uv run pytest -q \
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py \
  tests/unit_tests/live_voice/test_formal_history_writer.py \
  -k 'stable_sentence_final or contiguous'
```

- [ ] **Step 4: Implement exact final partition and coalescence**

Use Task 1 reconciliation; never fuzzy-match sanitized speech. Produce all
TEXT units before publishing the last cursor, so one contiguous TEXT ACK
authorizes the complete final history. `FormalHistoryWriter` concatenates the
validated contiguous contents and writes one idempotent `chat.final` record
whose ID includes response generation, final cursor and complete-content hash.
Mark `agent.sentence_final_reconciled` on exact completion and
`agent.sentence_candidate_discarded` whenever an unpromoted candidate is
removed; each mark remains first-occurrence-only in the existing probe.

- [ ] **Step 5: Verify compatibility and commit**

```bash
uv run pytest -q \
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py \
  tests/unit_tests/live_voice/test_formal_history_writer.py \
  tests/unit_tests/live_voice/test_conversation_runtime_loop.py \
  tests/unit_tests/live_voice/test_presentation_ledger.py
git add jiuwenswarm/server/live_voice/agent_conversation_runtime.py \
  jiuwenswarm/server/live_voice/formal_history_writer.py \
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py \
  tests/unit_tests/live_voice/test_formal_history_writer.py
git commit -m "feat(live-voice): reconcile stable speech with final history"
```

### Task 8: Serialize Stable-Sentence P2 Notifications

**Files:**
- Modify: `jiuwenswarm/server/live_voice/product_composition_registry.py`
- Modify: `tests/unit_tests/live_voice/test_product_composition_registry.py`
- Modify: `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs`

**Interfaces:**
- Consumes: Task 6/7 notification fields.
- Produces: exact wire fields `presentation_text`, `presentation_purpose` and
  optional `correction_of`, plus frontend dispositions `speech_segment`,
  `semantic_final` and `correction`.

- [ ] **Step 1: Write failing serializer tests**

Assert all P2 notifications include the three closed fields, using `null` when
absent. AUDIO stable-sentence notification requires candidate text and no
correction; semantic final requires a TEXT unit and complete `chat.final`;
correction requires an exact older `ResponseRef`. Invalid combinations fail
before returning a notification.

- [ ] **Step 2: Write failing frontend classifier tests**

```typescript
const early = classifyProductP2Notification(notification, false, true);
assert.equal(early.kind, 'speech_segment');
assert.equal(early.ack.surface, 'audio');
assert.equal(early.history_message_id, null);
```

Feature-off receiving any non-null purpose returns a visible
`PRODUCT_STABLE_SENTENCE_FEATURE_MISMATCH` failure with no play/ACK/history.

- [ ] **Step 3: Run RED**

```bash
uv run pytest -q tests/unit_tests/live_voice/test_product_composition_registry.py -k stable_sentence
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-integrated-web -- --test-name-pattern='stable sentence'
```

- [ ] **Step 4: Implement closed serialization and dispositions**

Extend `ProductP2NotificationDisposition` without weakening the existing
final/error validators. `speech_segment` carries exact AUDIO ACK and no history
ID; `semantic_final` carries the full visible final, optional tail speech and
TEXT ACK; `correction` carries the newer response and exact predecessor.

- [ ] **Step 5: Run GREEN and commit**

```bash
uv run pytest -q tests/unit_tests/live_voice/test_product_composition_registry.py -k 'stable_sentence or notification'
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-integrated-web
cd ../../../..
git add jiuwenswarm/server/live_voice/product_composition_registry.py \
  tests/unit_tests/live_voice/test_product_composition_registry.py \
  jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx \
  jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs
git commit -m "feat(live-voice): transport stable sentence presentations"
```

### Task 9: Implement Browser Playout, ACK and Correction Fencing

**Files:**
- Modify: `jiuwenswarm/channels/web/frontend/src/featureFlags.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/vite-env.d.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs`

**Interfaces:**
- Consumes: Task 8 dispositions and existing `playAgentText`/presentation ACK.
- Produces: sequential exact-unit play, AUDIO/TEXT ACK separation, final-tail
  playback, old-generation stop and correction playback.

- [ ] **Step 1: Write failing flag-off and early-play tests**

With the frontend flag true, an early segment calls `playAgentText` once with
candidate text, ACKs surface `audio` only after complete playout, does not call
`onProductVoiceMessage`, does not clear foreground-final waiting and does not
set semantic output. With flag false it performs zero calls/effects.

- [ ] **Step 2: Write failing compatible-final tests**

While the same response remains current, semantic final displays the complete
text once, speaks only `presentation_text` tail, then sends the last TEXT
cursor ACK. If tail is empty, it displays and ACKs without invoking TTS.

- [ ] **Step 3: Write failing replacement and late-chunk tests**

When a correction/newer generation arrives, stop the old `ProductP1VoiceRoute`
playout before starting correction TTS. Late Provider/downlink chunks and old
promise settlements produce zero ACK, history callback, successor capture or
active-response restoration.

- [ ] **Step 4: Run RED**

```bash
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-integrated-web -- --test-name-pattern='stable sentence|correction'
```

- [ ] **Step 5: Implement the frontend flag and per-unit queue**

Add:

```typescript
export const FEATURE_LIVE_VOICE_STABLE_SENTENCE_TTS =
  import.meta.env.VITE_FEATURE_LIVE_VOICE_STABLE_SENTENCE_TTS === 'true';
```

Replace the single ambiguous pending presentation slot only within the enabled
path with a bounded response-local queue keyed by
`response_id:generation:surface:unit_id`. Capacity is two: one active unit and
one final/correction handoff. Existing flag-off storage and ordering stay
unchanged.

- [ ] **Step 6: Implement exact stop/fence behavior**

Expose a bounded `stopAgentPlayout(response)` operation from
`ProductP1VoiceRoute` that increments its operation generation, stops current
playout/downlink and returns only after the local stop fence. It must not send
`response.cancel`, `round.cancel` or `task.cancel`.

- [ ] **Step 7: Run GREEN and commit**

```bash
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-integrated-web
npm run test:live-voice-accepted-checkpoint
cd ../../../..
git add jiuwenswarm/channels/web/frontend/src/featureFlags.ts \
  jiuwenswarm/channels/web/frontend/src/vite-env.d.ts \
  jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx \
  jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts \
  jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs \
  jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs
git commit -m "feat(live-voice): play and fence stable sentence audio"
```

### Task 10: Close Mismatch, Cancel and Recovery Semantics

**Files:**
- Modify: `jiuwenswarm/server/live_voice/agent_conversation_runtime.py`
- Modify: `jiuwenswarm/server/live_voice/product_composition_registry.py`
- Modify: `tests/unit_tests/live_voice/test_agent_conversation_runtime.py`
- Modify: `tests/unit_tests/live_voice/test_product_composition_registry.py`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs`

**Interfaces:**
- Consumes: delivery/ACK state and exact final mismatch.
- Produces: safe invalidation before delivery, conservative
  `partial_playout_unknown` after delivery, newer corrective response and exact
  replay/recovery behavior.

- [ ] **Step 1: Write the complete mismatch state table as failing tests**

Cover:

```text
candidate not promoted          -> discard, zero presentation/audio
promoted but not delivered      -> invalidate, replacement in same response
delivered but not AUDIO-ACKed    -> partial_playout_unknown + correction generation
AUDIO-ACKed                     -> immutable prefix + correction generation
exact prefix final              -> no correction, tail only
```

Delivery is a conservative server fact: once the P2 lease returned the unit,
the server does not infer that it remained unheard.

When an AUDIO ACK presents the outstanding unit before final, clear the bound
candidate and re-evaluate already-buffered text through the same policy. A
second unit may be promoted only after that ACK; it cannot bypass the one-unit
window.

- [ ] **Step 2: Write cancel/barge/recovery races**

Assert cancel, replacement, Exit, shutdown and terminal error fence the policy,
candidate, queued notification, TTS and late ACK. Saturated ordinary
notification capacity cannot block the critical stop/correction notification.
Replaying the exact notification/ACK is idempotent; conflicting replay fails
with zero effects.

- [ ] **Step 3: Implement corrective response allocation**

Allocate a new bounded response ID derived from the original request plus a
monotonic correction sequence, and obtain its strictly newer generation from
the existing response-generation owner. Mark
`agent.sentence_correction_started`, bind `correction_of`, present the complete
authoritative final once and never dispatch Agent/Tool/Task again.

- [ ] **Step 4: Preserve the cursor debt honestly**

No new field may claim word/frame position. Delivered-without-complete-ACK is
`partial_playout_unknown`; it is excluded from presented history. The
correction may repeat audible words, and the result documentation must state
that limitation rather than estimate a resume offset.

- [ ] **Step 5: Run the Tier-3 focused matrix and commit**

```bash
uv run pytest -q \
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py \
  tests/unit_tests/live_voice/test_product_composition_registry.py \
  tests/unit_tests/live_voice/test_formal_history_writer.py \
  tests/unit_tests/live_voice/test_conversation_runtime_loop.py \
  tests/unit_tests/live_voice/test_presentation_ledger.py
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-integrated-web
cd ../../../..
git add jiuwenswarm/server/live_voice/agent_conversation_runtime.py \
  jiuwenswarm/server/live_voice/product_composition_registry.py \
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py \
  tests/unit_tests/live_voice/test_product_composition_registry.py \
  jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs
git commit -m "fix(live-voice): fence stable sentence correction races"
```

### Task 11: Freeze A, Run A1/B/A2 and Decide the Candidate

**Files:**
- Create: `live-voice/evidence/STABLE_SENTENCE_AGENT_TTS_A_B_A_RESULT_2026-08-21.md`

**Interfaces:**
- Consumes: exact Task 5 A reference and exact Task 10 B source.
- Produces: compatible A1/B/A2 private reports, `comparison.json` and one
  sanitized `ACCEPT`, `REVISE` or `REJECT` result.

- [ ] **Step 1: Verify the already-tested neutral comparer contract**

Require identical runner hash, policy hash, fixture hash, environment/model/
voice profile and non-optimization flags. Require A1/A2 exact source equality,
B exact candidate source, at least five attempts per case, complete outcomes,
zero forbidden effects and A1/A2 target/total p50 drift at most 10%.

- [ ] **Step 2: Verify population selection changes only product behavior**

Inspect the Task 4 runner hash in A and B and require equality. A1/A2 omit the
candidate constructor keyword; B supplies only
`stable_sentence_tts_enabled=True`. The runner calls the existing
`compare_latency_reports_a_b_a` primitive and appends sentence counters without
adding component percentages or cross-clock durations.

- [ ] **Step 3: Create and verify the A reference worktree**

```bash
test ! -e /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-stable-sentence-agent-tts-a
git worktree add \
  /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-stable-sentence-agent-tts-a \
  latency/stable-sentence-agent-tts-screen-reference
```

Record the resolved 40-character commit. Do not rebase, merge or modify A.

- [ ] **Step 4: Run A1, B and A2 serially**

Run provider populations serially so they do not compete for Provider/network
resources. Use the same cases/config and five attempts per case. B runs in the
candidate worktree; A1/A2 run in the immutable A worktree.

```bash
export STABLE_SENTENCE_RUN_ROOT=/home/renan/openJiuwen-ai/live-voice-latency-runs/stable-sentence-a-b-a-20260821
export STABLE_SENTENCE_A_WORKTREE=/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-stable-sentence-agent-tts-a
export STABLE_SENTENCE_B_WORKTREE=/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-stable-sentence-agent-tts
install -d -m 700 "$STABLE_SENTENCE_RUN_ROOT"

cd "$STABLE_SENTENCE_A_WORKTREE"
uv run python scripts/live_voice/stable_sentence_causal_benchmark.py provider-run \
  --mode run --population A1 \
  --project-dir "$(realpath "$JIUWENSWARM_LATENCY_PROJECT_DIR")" \
  --cases tests/fixtures/live_voice/stable_sentence_provider_cases.json \
  --output "$STABLE_SENTENCE_RUN_ROOT/a1.json"

cd "$STABLE_SENTENCE_B_WORKTREE"
uv run python scripts/live_voice/stable_sentence_causal_benchmark.py provider-run \
  --mode run --population B \
  --project-dir "$(realpath "$JIUWENSWARM_LATENCY_PROJECT_DIR")" \
  --cases tests/fixtures/live_voice/stable_sentence_provider_cases.json \
  --output "$STABLE_SENTENCE_RUN_ROOT/b.json"

cd "$STABLE_SENTENCE_A_WORKTREE"
uv run python scripts/live_voice/stable_sentence_causal_benchmark.py provider-run \
  --mode run --population A2 \
  --project-dir "$(realpath "$JIUWENSWARM_LATENCY_PROJECT_DIR")" \
  --cases tests/fixtures/live_voice/stable_sentence_provider_cases.json \
  --output "$STABLE_SENTENCE_RUN_ROOT/a2.json"
```

- [ ] **Step 5: Compare and write evidence**

The evidence states first-PCM end-to-end values, not only percentages, and
labels Browser/human first audible `UNKNOWN`. `ACCEPT` requires the declared
gain, zero semantic/presentation integrity failure and no worse failure rate;
otherwise emit `REVISE` or `REJECT` without product credit.

```bash
cd "$STABLE_SENTENCE_B_WORKTREE"
uv run python scripts/live_voice/stable_sentence_causal_benchmark.py compare \
  --baseline-before "$STABLE_SENTENCE_RUN_ROOT/a1.json" \
  --candidate "$STABLE_SENTENCE_RUN_ROOT/b.json" \
  --baseline-after "$STABLE_SENTENCE_RUN_ROOT/a2.json" \
  --output "$STABLE_SENTENCE_RUN_ROOT/comparison.json"
```

- [ ] **Step 6: Commit the evidence**

```bash
git add live-voice/evidence/STABLE_SENTENCE_AGENT_TTS_A_B_A_RESULT_2026-08-21.md
git commit -m "docs(live-voice): record stable sentence A B A result"
```

### Task 12: Complete Verification, Reviews and Documentation Truth

**Files:**
- Modify: `live-voice/STATUS.md` only with exact accepted/rejected evidence
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`
- Modify: `live-voice/roadmap/STABLE_SENTENCE_AGENT_TTS_IMPLEMENTATION_PLAN_2026-08-21.md`
- Create: `live-voice/reviews/STABLE_SENTENCE_AGENT_TTS_REVIEW_2026-08-21.md`

**Interfaces:**
- Consumes: complete branch diff, Task 11 result and root `TESTING.md`.
- Produces: exact review record, synchronized current truth and a clean local
  branch handoff. No remote update.

- [ ] **Step 1: Run focused and affected backend verification**

```bash
uv run pytest -q \
  tests/unit_tests/live_voice/test_stable_sentence_policy.py \
  tests/unit_tests/live_voice/test_stable_sentence_causal_benchmark.py \
  tests/unit_tests/live_voice/test_latency_probe.py \
  tests/unit_tests/live_voice/test_latency_probe_report.py \
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py \
  tests/unit_tests/live_voice/test_product_composition_registry.py \
  tests/unit_tests/live_voice/test_formal_history_writer.py \
  tests/unit_tests/live_voice/test_conversation_runtime_loop.py \
  tests/unit_tests/live_voice/test_presentation_ledger.py
uv run ruff check \
  jiuwenswarm/server/live_voice/stable_sentence_policy.py \
  jiuwenswarm/server/live_voice/agent_conversation_runtime.py \
  jiuwenswarm/server/live_voice/product_composition_registry.py \
  jiuwenswarm/server/live_voice/formal_history_writer.py \
  scripts/live_voice/stable_sentence_causal_benchmark.py
```

- [ ] **Step 2: Run affected frontend verification**

```bash
cd jiuwenswarm/channels/web/frontend
npm run test:live-voice-integrated-web
npm run test:live-voice-latency-probe
npm run test:live-voice-accepted-checkpoint
npm run build
cd ../../../..
```

- [ ] **Step 3: Perform the cold complete-diff review**

Review from the Task 5 A reference through current B. Check every applicable
P/N/B/S/T/C/R/I/F/K/X dimension, exact feature-off behavior, correction
generation, history coalescence, late Provider chunks, zero forbidden effects,
privacy and measurement labels. Record commands and exact commit.

- [ ] **Step 4: Obtain independent Tier-3 module review**

The reviewer receives the spec, this plan, exact A/B diff, focused test output
and raw-artifact location without credentials. Fix Critical/Important findings
and rerun only materially affected checks; record limitations rather than
claiming unavailable physical evidence.

- [ ] **Step 5: Synchronize documentation**

If Task 11 is `ACCEPT`, update only the affected STATUS capability rows with
exact source/evidence and retain physical Browser/cursor gaps. If `REJECT`,
record the rejected candidate in the inventory without upgrading STATUS. Mark
completed plan checkboxes truthfully; do not mark conditional tasks complete
when the Task 5 gate stopped them.

- [ ] **Step 6: Run documentation and repository checks**

```bash
git diff --check
git status --short --branch
git ls-files docs/zh/live-voice
```

Resolve every changed local Markdown link and confirm the last command prints
no tracked duplicate.

- [ ] **Step 7: Commit the closure batch**

```bash
git add live-voice/STATUS.md \
  live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md \
  live-voice/roadmap/STABLE_SENTENCE_AGENT_TTS_IMPLEMENTATION_PLAN_2026-08-21.md \
  live-voice/reviews/STABLE_SENTENCE_AGENT_TTS_REVIEW_2026-08-21.md
git commit -m "docs(live-voice): close stable sentence latency candidate"
```

- [ ] **Step 8: Prepare the handoff without pushing**

Report branch, exact commits, A reference, status, diff summary, tests, review,
A1/B/A2 absolute results, cursor/physical exclusions and private artifact root.
Any push remains a separate exact remote/ref approval under root `AGENTS.md`.
