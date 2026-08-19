# Live Voice minimal latency probe specification

> **Status:** APPROVED DESIGN — implementation and current-source measurement
> have not started.
>
> **Date:** 2026-08-19
>
> This specification defines the immediate experimental measurement loop for
> the real Integrated Web voice path. The broader
> [full probe specification](FULL_LATENCY_PROBE_SPEC_2026-08-19.md) and
> [full implementation plan](FULL_LATENCY_PROBE_IMPLEMENTATION_PLAN_2026-08-19.md)
> remain future architecture references; they are not the current probe scope
> or acceptance contract. The
> [latency optimization plan](LATENCY_OPTIMIZATION_PLAN_2026-08-18.md) owns the
> later optimization order and product acceptance targets.

## 1. Purpose

The immediate objective is a minimal, direct, repeatable loop:

`measure → establish baseline → change one optimization → re-measure → compare`.

The probe records start/end timestamps at stable boundaries of the real voice
pipeline, links them to the same voice round, and reports stage-by-stage and
total latency. It must show whether one optimization:

- reduced the targeted stage and total response time;
- moved an equivalent wait to another stage;
- introduced a failure, fallback, underrun, rebuffer, cancellation, or other
  guardrail regression; or
- produced evidence too weak or incompatible to decide.

The probe is an experimental diagnostic, not a product observability platform.
Probe state never grants Speech, Agent, Tool, Task, media, presentation,
history, ACK, cancellation, or next-turn authority.

## 2. Scope and non-goals

The first implementation includes only:

- one small `LatencyMark` record;
- bounded in-memory Browser, Gateway, and Agent Server recorders;
- one post-terminal Browser batch;
- one JSONL batch file per producer process;
- fixed Browser-clock segments and local same-clock drill-downs;
- JSON, CSV, and Markdown reports;
- baseline/candidate comparison under a compatible run configuration; and
- five fixed benchmark profiles.

It does not include:

- a dynamic critical-path or hot-path engine;
- a DAG, parent operations, predecessor operations, or inferred dependencies;
- a general multidimensional catalog or event-budget calculus;
- derived span, graph, measurement, and aggregate protocols;
- generic background Task or terminal-notification journeys;
- a production exporter, SLO system, retention platform, or public telemetry;
- cross-process clock synchronization;
- a physical-audio observer implementation;
- product optimization code; or
- any product-readiness, feature-complete, or Production-readiness claim.

The full documents may inform a later productized system, but the minimal probe
does not have to implement a subset-compatible version of every full schema.

## 3. Fixed benchmark profiles

Every baseline and confirmatory candidate run declares these profiles
independently:

| Profile ID | Measured foreground outcome |
|---|---|
| `dialogue_no_tool` | Short ordinary dialogue response without Tool execution |
| `dialogue_with_tool` | Dialogue response that uses one declared Tool path |
| `task_create` | Supported Task create command through authoritative foreground acknowledgement presentation |
| `task_status` | Supported Task status command through authoritative foreground response presentation |
| `task_cancel` | Supported Task cancel command through authoritative foreground response presentation |

Task profiles stop at the foreground response, playout receipt, and next-turn
transition. Background attempt execution, result application, Task terminal
state, and later terminal notification are outside v0 latency totals.

Every profile uses a tracked public `input_case_id`. Runtime transcript,
prompt, response, Tool content, Task description, and Task result content are
forbidden from probe records.

## 4. Measurement truths

### 4.1 Independent clocks

Windows Browser, WSL Gateway, and Agent Server have independent monotonic
clocks. A numeric duration is valid only when both boundary marks have the same
`clock_domain_id`.

Cross-component marks may demonstrate correlation and ordering through exact
voice identities. They must not be subtracted or presented as an exact
duration. Wall time is not a release-quality substitute for monotonic time.

The Browser provides the continuous additive timeline. Gateway and Agent Server
provide local drill-downs that explain portions of that Browser-observed time;
local drill-downs are not added to the Browser total.

### 4.2 Operational totals

The required response total is:

`browser.eot_received → browser.playout_first_frame_started_estimate`.

The required round total is:

`browser.eot_received → browser.next_turn_capture_activated`.

Both are exact arithmetic in the Browser performance clock, subject to the
explicit uncertainty of the first-frame-start estimate. Neither is called
physical first audible.

An external physical observer may later report
`physical speech end → physical first audible` from one physical clock. Its
absence does not fail this minimal probe and the Browser estimate must never be
renamed as that physical metric.

### 4.3 Missing and failed observations

A missing boundary produces `unknown`, never zero. Failed, cancelled, fallback,
underrun, and rebuffer rounds remain in the attempt denominator. A report may
calculate latency percentiles only from successful numeric samples, while
showing the other outcome counts beside them.

## 5. Run and round identity

One experiment run has one immutable `run.json` and a random non-secret
`run_id`. Each attempted profile round has a zero-based `round_index` within
that profile.

Marks retain the applicable existing identities:

- `correlation_id` and `interaction_id` identify the product interaction;
- `activation_id` and `activation_generation` bind pre-commit media;
- `turn_id` binds committed input when it exists;
- `response_id` and `response_generation` bind presentation, TTS, downlink,
  playout, and ACK when they exist; and
- `task_id` binds a supported foreground Task response when it exists.

The probe does not mint replacements for these identities. A pre-commit mark
may lack `turn_id`; a pre-response mark may lack response identity. The submit
boundary, which carries both the media/interaction binding and committed turn
binding, supplies the exact transition. Marks are never joined by text,
timestamp proximity, most-recent state, or display order.

Each producer process/page has a random `source_instance_id`, one
`clock_domain_id`, and a contiguous `mark_index` within each emitted batch. A
batch has a random `batch_id`; an identical retry is idempotent and conflicting
bytes under the same `batch_id` are rejected by the probe.

## 6. Minimal closed records

### 6.1 Latency mark

```text
LatencyMark {
  schema_version: "live-voice.latency-probe.v0"
  run_id: bounded opaque string
  profile_id: closed benchmark profile
  input_case_id: manifest-declared public token
  round_index: non-negative integer

  source_instance_id: bounded opaque string
  mark_index: non-negative integer
  component: "browser" | "gateway" | "agent_server"
  clock_domain_id: bounded opaque string
  point: core point or run-declared experiment point
  monotonic_ms: finite non-negative number
  uncertainty_ms: finite non-negative number | null
  outcome: "observed" | "completed" | "failed" | "cancelled" |
           "fallback" | "unknown"
  reason_code: closed stable reason | null

  correlation_id: bounded opaque string
  interaction_id: bounded opaque string
  activation_id: bounded opaque string | null
  activation_generation: non-negative integer | null
  turn_id: bounded opaque string | null
  response_id: bounded opaque string | null
  response_generation: non-negative integer | null
  task_id: bounded opaque string | null
}
```

Objects are closed. Unknown keys, arbitrary metadata, exception text, and raw
payload fragments are rejected. `uncertainty_ms` is non-null only for an
estimated observation such as Browser playout start.

The initial stable reason codes are:

- `FEATURE_OFF`, `CAPACITY`, `EXPORT_FAILED`, `BATCH_CONFLICT`;
- `MISSING_MARK`, `DUPLICATE_MARK`, `SEQUENCE_GAP`, `IDENTITY_MISMATCH`;
- `CROSS_CLOCK`, `FAILED`, `CANCELLED`, `FALLBACK`;
- `UNDERRUN`, `REBUFFER`, `TIMEOUT`, `INCOMPATIBLE_RUN`; and
- `INSUFFICIENT_SAMPLES`.

An implementation maps an internal exception to one of these codes and never
retains the exception message or traceback.

### 6.2 Latency batch

```text
LatencyBatch {
  schema_version: "live-voice.latency-batch.v0"
  batch_id: bounded opaque string
  run_id: bounded opaque string
  profile_id: closed benchmark profile
  input_case_id: manifest-declared public token
  round_index: non-negative integer
  source_instance_id: bounded opaque string
  component: closed component
  phase: "browser_round" | "gateway_stt" | "gateway_tts" |
         "agent_foreground"
  terminal_outcome: "completed" | "failed" | "cancelled" | "unknown"
  marks: bounded list[LatencyMark]
}
```

Browser emits one `browser_round` batch after the round terminal or stable
failure. Gateway may emit one STT and one TTS batch at their local terminals.
Agent Server emits one foreground batch after presentation dispatch or stable
failure. No producer writes or sends one record per event.

The initial maximum is 64 marks per batch. Capacity exhaustion records one
probe-only `CAPACITY` outcome when space remains, stops accepting further
marks for that batch, and cannot fail the product operation.

## 7. Core Browser timeline

The following points are fixed across baseline and every candidate:

| Order | Point | Owned meaning |
|---:|---|---|
| B0 | `browser.eot_received` | Current-generation EOT control accepted by the Browser product route |
| B1 | `browser.stt_final_received` | Bound authoritative streaming STT final accepted by the Browser |
| B2 | `browser.commit_submit_started` | Unified committed-input request began |
| B3 | `browser.presentation_received` | Bound authoritative foreground PresentationUnit reached the Browser |
| B4 | `browser.tts_request_started` | Formal synthesis request began for that PresentationUnit |
| B5 | `browser.downlink_first_frame_received` | First valid bound downlink frame reached the Browser receiver |
| B6 | `browser.playout_first_frame_scheduled` | WebAudio accepted the first frame schedule |
| B7 | `browser.playout_first_frame_started_estimate` | Browser clock estimates first-frame rendering began, with uncertainty |
| B8 | `browser.playout_completed` | Exact bound playout reached its local successful terminal |
| B9 | `browser.playout_ack_received` | Valid bound playout-receipt response returned |
| B10 | `browser.next_turn_capture_activated` | Prepared successor capture became the active next-turn input |

Each point occurs at most once per successful round identity. A repeated point
with conflicting time or binding makes that segment unknown.

### 7.1 Fixed Browser segments

| Segment ID | Start → end | Component | Phase tags | Primary capability |
|---|---|---|---|---|
| `eot_to_stt_final` | B0 → B1 | Browser | P1, P2 | `speech_recognition` |
| `stt_final_to_submit` | B1 → B2 | Browser | P1, P2, P3 | `integrated_web` |
| `submit_to_presentation` | B2 → B3 | Browser | P2, P3 | `cross_component_seam` |
| `presentation_to_tts_request` | B3 → B4 | Browser | P1, P2, P3 | `integrated_web` |
| `tts_request_to_first_downlink` | B4 → B5 | Browser | P1, P2, P3 | `cross_component_seam` |
| `first_downlink_to_schedule` | B5 → B6 | Browser | P1 | `audio_io` |
| `schedule_to_start_estimate` | B6 → B7 | Browser | P1 | `audio_io` |
| `estimated_start_to_playout_complete` | B7 → B8 | Browser | P1 | `audio_io` |
| `playout_to_ack` | B8 → B9 | Browser | P1, P2, P3 | `cross_component_seam` |
| `ack_to_next_capture` | B9 → B10 | Browser | P1, P2 | `conversation_runtime` |
| `response_total` | B0 → B7 | Browser | P1, P2, P3 | `integrated_web` |
| `round_total` | B0 → B10 | Browser | P1, P2, P3 | `integrated_web` |

`phase_tags` are filters only. Reports never sum P1, P2, and P3 as exclusive
buckets. Browser segments and totals are alternative resolutions; reports do
not add `response_total` to its child segments.

Segments ending at B7 are estimated and retain B7's uncertainty. Other valid
same-Browser-clock segments are exact observations. In particular,
`response_total` is an operational estimate while `round_total` is an exact
Browser-clock lifecycle duration; neither is physical first-audible truth.

## 8. Core local drill-downs

Local drill-downs use stable points but do not form a universal pipeline graph.
Only an explicitly paired same-clock segment is numeric.

### 8.1 Browser capture, settlement, and concurrency

Core points:

```text
browser.capture_start_requested
browser.capture_device_started
browser.media_socket_attached
browser.capture_first_frame_sent
browser.capture_first_ack_received
browser.capture_stop_requested
browser.capture_stopped
browser.uplink_last_frame_sent
browser.uplink_last_ack_received
browser.uplink_closed
browser.successor_capture_requested
browser.successor_capture_ready
browser.downlink_attach_started
browser.downlink_attached
browser.playout_underrun
browser.playout_rebuffer
```

Fixed local segments:

| Segment ID | Start → end | Phase tags | Primary capability |
|---|---|---|---|
| `capture_device_startup` | capture start requested → device started | P1 | `audio_io` |
| `capture_first_frame_readiness` | capture start requested → first ACK received | P1, P2 | `realtime_media` |
| `eot_to_capture_stopped` | EOT received → capture stopped | P1 | `audio_io` |
| `eot_to_uplink_closed` | EOT received → uplink closed | P1, P2 | `realtime_media` |
| `successor_capture_readiness` | successor capture requested → ready | P1, P2 | `realtime_media` |
| `downlink_attach` | downlink attach started → attached | P1, P2 | `realtime_media` |

These points are sufficient to evaluate the planned Provider-final/local-media
overlap and successor-capture/downlink decoupling without a gate graph.

### 8.2 Gateway STT/VAD

Core points:

```text
gateway.stt_request_started
gateway.stt_provider_transport_open
gateway.stt_session_ready
gateway.vad_speech_stopped
gateway.eot_control_sent
gateway.stt_final_available
```

Fixed local segments:

| Segment ID | Start → end | Phase tags | Primary capability |
|---|---|---|---|
| `stt_transport_open` | STT request started → Provider transport open | P1, P2 | `speech_recognition` |
| `stt_session_configuration` | Provider transport open → session ready | P1, P2 | `speech_recognition` |
| `provider_eot_to_control_send` | Provider speech stopped → EOT control sent | P1, P2 | `interaction_intelligence` |
| `provider_eot_to_stt_final` | Provider speech stopped → STT final available | P1, P2 | `speech_recognition` |

This does not claim physical speech-end latency. Controlled VAD experiments
must pair these timings with their declared corpus outcome for false/missed EOT.

### 8.3 Agent Server foreground path

Core points:

```text
agent.commit_submit_received
agent.commit_accepted
agent.route_resolved
agent.agent_started
agent.agent_first_delta
agent.tool_execution_started
agent.tool_execution_completed
agent.agent_final
agent.task_command_accepted
agent.presentation_produced
agent.presentation_dispatched
```

Fixed local segments:

| Segment ID | Start → end | Applicable profile | Phase tags | Primary capability |
|---|---|---|---|---|
| `commit_admission` | submit received → commit accepted | all | P2, P3 | `conversation_runtime` |
| `semantic_routing` | commit accepted → route resolved | all | P2, P3 | `interaction_intelligence` |
| `route_to_agent_start` | route resolved → Agent started | dialogue profiles | P2 | `agent_bridge` |
| `agent_to_first_delta` | Agent started → first delta | dialogue profiles | P2 | `agent_bridge` |
| `agent_to_final` | Agent started → Agent final | dialogue profiles | P2 | `agent_bridge` |
| `tool_execution` | Tool execution started → completed | `dialogue_with_tool` | P2 | `agent_bridge` |
| `agent_final_to_presentation` | Agent final → presentation produced | dialogue profiles | P2 | `conversation_runtime` |
| `task_command` | route resolved → Task command accepted | Task profiles | P3 | `voice_task_bridge` |
| `task_command_to_presentation` | Task command accepted → presentation produced | Task profiles | P2, P3 | `cross_component_seam` |
| `presentation_dispatch` | presentation produced → dispatched | all | P2, P3 | `conversation_runtime` |

Tool and Task points observe existing authoritative owners. The probe cannot
create a Tool call, Task command, acknowledgement, or PresentationUnit.

### 8.4 Gateway synthesis and downlink

Core points:

```text
gateway.tts_request_received
gateway.tts_provider_transport_open
gateway.tts_provider_first_audio
gateway.downlink_ticket_ready
gateway.downlink_first_frame_sent
```

Fixed local segments:

| Segment ID | Start → end | Phase tags | Primary capability |
|---|---|---|---|
| `tts_transport_open` | TTS request received → Provider transport open | P1, P2, P3 | `speech_synthesis` |
| `tts_open_to_first_audio` | Provider transport open → first audio | P1, P2, P3 | `speech_synthesis` |
| `tts_time_to_first_audio` | TTS request received → first audio | P1, P2, P3 | `speech_synthesis` |
| `tts_first_audio_to_ticket` | Provider first audio → downlink ticket ready | P1, P2, P3 | `realtime_media` |
| `tts_first_audio_to_first_send` | Provider first audio → first downlink frame sent | P1, P2, P3 | `realtime_media` |

## 9. Experiment-specific marks

The core points and segments remain stable across all runs. One optimization
may add bounded marks named:

`experiment.<experiment_id>.<fact>`.

Every experiment point must be declared in `run.json` with:

```text
point
component
paired_segment_id | null
start_point | null
end_point | null
```

A paired experiment segment is numeric only when its two marks have the same
clock domain. Undeclared `experiment.*` marks are rejected. Experiment marks
do not rename, replace, or change the calculation of a core segment.

Examples owned by later optimization packets include adaptive-buffer readiness,
discarded sentence prefetch, first stable sentence, and inter-sentence gap.
Their presence in a run config does not authorize the optimization itself.

## 10. Collection and storage

The probe is default-off and development-only. Feature-off creates no recorder,
mark callback, batch request, or output file.

When enabled:

1. each producer records marks in a bounded in-memory list;
2. Browser emits one batch only after B10 or a stable failed/cancelled terminal;
3. Gateway writes the accepted Browser batch as one JSONL line;
4. Gateway writes each local STT/TTS batch as one JSONL line;
5. Agent Server writes its local foreground batch as one JSONL line; and
6. the offline reducer reads all files after the run.

The private output layout is:

```text
<output-root>/<run-id>/
  run.json
  browser.jsonl
  gateway.jsonl
  agent.jsonl
```

`<output-root>` is a private runtime setting and never appears in tracked
evidence. Gateway and Agent Server write separate files; no two processes share
an append handle. Full JSON serialization, file I/O, reporting, and percentile
calculation are outside the measured event path.

The Browser uses one development-only Gateway batch method. The handler accepts
only a bounded closed batch for the dispatcher-owned session and declared run.
It never calls media, Speech, Agent, Tool, Task, presentation, history, or ACK
owners. A rejected or failed batch cannot fail the voice round.

## 11. Run configuration

`run.json` contains only reproducibility and comparison facts:

```text
schema_version
run_id
git_commit
source_state: clean | docs_only_dirty | product_code_dirty
environment_profile
browser_family_and_version
browser_os_class
gateway_runtime_class
agent_runtime_class
stt_provider_and_model
tts_provider_and_model
audio_format
vad_configuration
playout_configuration
allowlisted_feature_flags
cold_or_warm
input_case_ids
profile_ids
intended_attempts
required_successes
experiment | null
```

An optional experiment contains:

```text
experiment_id
target_segment
target_statistic: p50_ms | p95_ms
minimum_improvement_ms
response_total_minimum_improvement_ms
guardrails
declared_experiment_points
```

Each guardrail is closed to:

```text
metric: p50_ms | p95_ms | failure_rate | fallback_rate |
        underrun_rate | rebuffer_rate | cancellation_rate
segment_id: fixed segment | null
maximum_regression: finite non-negative number
```

It supports comparison only; it does not encode product configuration changes
or authorize implementation.

Credentials, URLs, private endpoints, hostname, username, filesystem path, raw
device ID, database identity, audio, text, prompt, response, Tool content, Task
content, exception, and arbitrary metadata are forbidden.

A `product_code_dirty` run is exploratory and cannot become a baseline or
confirmatory candidate. `docs_only_dirty` is comparable only if no runtime or
build input is dirty.

## 12. Reduction and reporting

The reducer performs a fixed sequence:

1. validate `run.json` and every closed batch/mark;
2. reject conflicting batch IDs and incompatible run/profile identities;
3. validate contiguous `mark_index` within each batch;
4. group by run, profile, round, and exact authoritative binding;
5. pair only the fixed segment boundaries and declared experiment boundaries;
6. calculate numeric duration only for one compatible clock domain;
7. retain missing/cross-clock/incompatible segments as `unknown`; and
8. calculate run summaries.

For every profile and segment, report:

```text
attempts
successful_samples
unknown
failed
cancelled
fallback
underrun
rebuffer
minimum_ms
p50_ms
p95_ms
maximum_ms
```

Percentiles use nearest rank over sorted successful numeric samples. Cold and
warm populations are never pooled.

The required outputs are:

- `report.json` for reproducible machine comparison;
- `report.csv` for stage/time-series analysis; and
- `report.md` for one table and simple waterfall per profile.

The report includes `component`, `phase_tags`, and `primary_capability` for each
segment. These dimensions support filtering and graphs; they are not additional
latency totals.

## 13. Baseline/candidate comparison

Baseline and candidate must match on:

- schema version and fixed segment definitions;
- environment profile;
- Browser/OS and Gateway/Agent runtime classes;
- STT/TTS Provider and model;
- audio format, VAD, playout, and allowlisted route flags;
- cold/warm classification;
- profile and public input case; and
- required sample policy.

The Git commit is expected to differ. A comparison shows baseline/candidate
p50 and p95, absolute/relative deltas, attempt/sample counts, and all guardrail
count/rate changes.

When an experiment declares a target and guardrails, the comparison classifies:

- `improved`: the target reaches its declared gain, total does not regress, and
  every guardrail passes; specifically, `response_total` reaches its declared
  minimum gain;
- `shifted`: the target segment improves but `response_total` does not reach
  its declared gain and another fixed Browser stage increases;
- `regressed`: total or a guardrail violates its declared bound; or
- `inconclusive`: runs are incompatible, samples are insufficient, or a
  required segment is unknown.

The reducer does not invent a universal improvement threshold.

## 14. Execution protocol

The warm path is the normal optimization loop:

- fast iteration: five attempted rounds per profile;
- confirmatory comparison: at least 20 successful rounds per profile; and
- failures remain in the attempt denominator rather than being retried away.

Cold is recorded with at least 20 successful samples per profile in the initial
baseline and repeated only for a candidate that already passed warm
confirmation. Cold and warm reports remain separate.

Each optimization uses one declared change at a time, the same environment,
configuration, public input cases, and measurement code. If instrumentation or
fixed segment definitions change, the baseline must be re-run before comparing
product optimization results.

The first accepted output of this packet is a current-source baseline, not a
latency improvement.

## 15. Failure isolation and privacy

The recorder and batch path must be best-effort relative to product behavior:

- capacity stops probe collection for that batch only;
- export failure leaves the local diagnostic incomplete;
- a missing producer file makes affected segments unknown;
- malformed, wrong-run, wrong-session, stale-generation, or conflicting data
  is rejected by the probe only;
- no probe retry may repeat a product request; and
- no probe outcome may acknowledge media/presentation, advance a cursor,
  commit input, select a route, dispatch work, or activate next-turn capture.

Tests inject recognizable private sentinels at Browser, Gateway, Provider,
Agent, Tool, Task, and error boundaries and prove that none appears in memory
snapshots, batch payloads, JSONL, reports, logs, or error messages.

## 16. Probe acceptance

Implementation acceptance follows the applicable Tier-3 shared-protocol rules
in [root TESTING](../../TESTING.md), scoped to this diagnostic seam rather than
the future full platform.

Acceptance requires:

1. deterministic tests for every fixed segment and both totals;
2. missing marks produce `unknown`, not zero;
3. cross-clock pairs produce no numeric duration;
4. duplicate, sequence-gap, wrong-run, wrong-round, wrong-session,
   stale-generation, and conflicting-batch cases are explicit;
5. feature-off allocates and emits nothing probe-specific;
6. capacity, serialization, file, and batch failure have zero product side
   effects;
7. forbidden sentinels appear on no output surface;
8. existing capture, STT, committed-input, Agent/Tool, Task, presentation, TTS,
   playout, ACK, and next-turn tests retain their authoritative behavior with
   the probe enabled and disabled;
9. all five fixed profiles produce one real warm current-source run;
10. the accepted warm baseline has at least 20 successful samples per profile,
    with failures and guardrail counts retained;
11. the initial cold baseline has at least 20 successful samples per profile
    and remains separate; and
12. the report binds the exact measured Git commit and compatible run config.

Passing these checks establishes a measurement oracle. It does not pass a
latency target or authorize the next optimization automatically.

## 17. Implementation ownership anchors

The later implementation plan starts from these current owners:

- Browser round orchestration, EOT, successor capture, TTS handoff, playout,
  ACK, and next-turn transition:
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`;
- Browser audio schedule/start estimate and underrun/rebuffer:
  `formal/adapters/browserAudioIOAdapter.ts` under the same directory;
- Browser dedicated uplink/downlink:
  `formal/adapters/browserDedicatedMediaRoute.ts` and
  `formal/adapters/browserGatewayMediaTransport.ts`;
- Integrated foreground presentation and commit submission:
  `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`
  and `formal/unifiedCommittedInputOwner.ts`;
- Gateway STT/VAD/EOT:
  `jiuwenswarm/gateway/live_voice/streaming_speech_route.py`,
  `dedicated_media_registration.py`, and
  `jiuwenswarm/server/live_voice/openai_streaming_speech.py`;
- committed input, routing, Agent/Tool, Task foreground response, and
  PresentationUnit:
  `jiuwenswarm/server/live_voice/product_composition_registry.py`,
  `voice_task_bridge.py`, and `agent_conversation_runtime.py`; and
- Gateway synthesis/downlink:
  `jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py` and
  `streaming_synthesis_route.py`.

The plan must prefer a small shared mark/recorder helper and owner-local calls.
It must not import the future full graph/catalog architecture into the minimal
packet.

## 18. Accepted design decisions

The approved v0 decisions are:

1. retain the `FULL_` documents unchanged as future references;
2. use a minimal active spec and later minimal implementation plan;
3. include all five dialogue/Tool/Task foreground profiles from the baseline;
4. make the Browser operational response and round totals mandatory and the
   physical observer optional;
5. use one post-terminal Browser batch plus separate Gateway/Agent JSONL;
6. keep a fixed core marker set and allow only run-declared namespaced
   experiment marks;
7. use five warm rounds for iteration and at least 20 successful warm rounds
   for confirmation;
8. measure cold at baseline and for confirmed candidates, separately from warm;
9. retain `component`, `phase_tags`, and `primary_capability` as static report
   labels rather than a multidimensional runtime catalog; and
10. let each experiment declare its target and guardrails while keeping product
    optimization implementation outside the probe.
