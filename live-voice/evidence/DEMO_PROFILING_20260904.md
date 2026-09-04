# Demo profiling and failure diagnosis — 2026-09-04

## Scope recorded before implementation

Baseline: `af1b47d638968e80e676c8c80f5e48647cd2e58b`.
The user requests diagnostic code sufficient to profile every Demo pipeline
boundary and investigate failures after rehearsal without another instrumentation
change. This supersedes the earlier diagnostic-only segmentation checkpoint as
the current implementation packet; it does not authorize a segmentation policy.

Owned capability: Observability / benchmark / latency, Tier 2. Owned product
surfaces are passive diagnostic hooks at browser startup/capture/media/RPC/
playout, Gateway forwarding/recognition/synthesis, semantic context/model calls,
Agent/model/tool progress, Task execution and notification/presentation boundaries.
Owned support surfaces are bounded local browser export, a content-free backend
diagnostic stream, offline timeline/error/coverage analysis, focused tests and
the runbook. Existing observation and business wire schemas stay unchanged.

Intended behavior:

- Normal rehearsals record timing without enabling a special L0 corpus run.
  Existing fine-grained audio diagnostics are retained. Parent/child spans,
  request/capture/response/Task identities and per-process/browser clock domains
  support exact local durations and explicit cross-component joins.
- Start and settlement evidence distinguish success, rejected results, failure,
  timeout, cancellation and incomplete operations. Model first output, every
  observed tool call/result, fallback and cleanup are visible. A function return,
  enqueue or playback scheduling is never reported as business completion or
  physical audibility.
- Browser evidence survives refresh within bounded same-tab retention and has
  a download action. Offline analysis combines exports with existing service
  logs, reports slow stages and failure breadcrumbs, exposes missing/dropped
  evidence, and generates a shareable local timeline without network access.
- Observers have bounded storage, bounded queues and passive failure handling.
  No transcripts, prompts, tool arguments/results, PCM, keys, tickets, URLs,
  arbitrary exception strings or content hashes are exported. Safe error codes,
  exception classes and source locations support diagnosis.

Exclusions: business/Task/Store authority, new VAD or interruption classifiers,
split/merge or successor-capture policy, altered timeouts/retries/buffers, model
or credential changes, production deployment, remote-ref updates, OS/Provider
internals and physical microphone-to-ear timing that software cannot observe.
No claim that finite instrumentation can identify every external root cause.

Acceptance: positive and rejected/failure/cancel paths keep identical calls,
values and side effects; concurrent identities and parent spans remain isolated;
missing/dropped/expired evidence is not fabricated; stream early-close and
observer failures preserve cleanup; storage/export/import stay bounded and
content-free; malicious imported data cannot execute in the offline report.
Verify real local HTTP/WebSocket and actual model adapter seams with synthetic
transport, affected regressions and frontend build. Independent review is
required by root TESTING.md; record its actual outcome. Real Provider and human
Demo acceptance remain distinct from instrumentation verification.

## Implementation and verification

Implemented on the stated baseline as one passive Observability batch:

| Boundary | Evidence now recorded |
|---|---|
| Browser | getUserMedia, AudioContext resume/output selection, Worklet load, capture/media state, ordinary Live Voice RPC settlement, existing sampled PCM queue and playback metrics, main-thread long tasks and browser failure markers |
| Gateway / Speech | Recognition selection/open/wait-EOT/final/abort/provider-close; streaming/batch and HTTP phases, upload/send lock/encode/socket/transport queues, synthesis open/consume/first-audio/retirement |
| Semantic / Agent | Context/history/pending resolution, model configuration, each existing semantic attempt, Agent session/configuration/dispatch/round/progress, spoken revision |
| Model / Tool | Each foreground and dedicated background Code Agent model invoke/stream, including timings after the existing 16-call foreground content-inspection bound; first chunk, chunk count and largest gap; every observed tool call/result keyed by exact existing call and request IDs |
| Task / notification | Dispatch/attempt/adjust/cancel, worktree/artifact/project-effect/cleanup boundaries, notification wait/prepare/deliver and presentation acknowledgement |
| Analysis | Bounded refresh-retained browser journal + UI download, sanitized multi-file imports, exact-clock spans and tool/HTTP/model pairs, failure source breadcrumbs, retention warnings, HTML/JSON/Chrome Trace output |

The new shared recorder uses `perf_counter()` for sub-millisecond local
observations on Windows; timestamps and process/tab clock IDs distinguish it
from historical records. Source contexts are task-local and cross `to_thread`
without new wire fields. A sampled AudioContext start observer is fenced by
current playback ownership and stops after two seconds; it is not an audible
start or acknowledgement authority. Foreground and dedicated background model
first-chunk wait is separate from the largest inter-chunk gap; the first chunk
does not inflate the gap metric. Dedicated background wrappers inspect no
model input or output content and never stack across adjustment requests. Detailed content-equality observation keeps
its original bound; additional model records contain counts/timing only.

Returned calls are labelled `returned`, not successful business outcomes. Explicit
rejected envelopes, structured error codes/reasons, exceptions, timeout/cancel,
missing start/tail, duplicate starts and dropped records remain distinguishable.
HTTP phases and tool spans are paired only with exact identities in one clock
domain. No cross-process monotonic subtraction or guessed missing duration is
performed. Missing-start spans are instants in Chrome Trace rather than bars
starting at the wrong time.

### Verification record

- New profiling/import suite: 21 PASS. Covers preserved return/error/cancel,
  concurrent parent/child scope, thread propagation, faulty observers/getters,
  exact clock/model/HTTP/tool pairing, backward wall-clock ordering, incomplete
  and duplicate evidence, privacy/import injection and actionable CLI errors.
  Background stream early-close from a foreign task preserves original Task IDs,
  closes the underlying stream once and never stacks wrappers across requests.
- Browser diagnostic suite: 7 PASS. Covers bounded retention and refresh import,
  sanitization, quota denial, faulty clock/metadata and original action counts.
- Browser Audio I/O + Worklet suite: 107 PASS. Adds direct proof that a late
  diagnostic timer after close cannot create/replay audio or cancel business work.
- Dedicated media + product P1 routes: 145 PASS, including interruption,
  capture rotation, current-owner recovery and existing forbidden-effect oracles.
- Agent/model/facade verification: 133 PASS initially; two unmarked async tests
  required restoring the repository `asyncio_mode=auto` setting removed with
  the coverage-heavy addopts override. Their corrected rerun: **2 PASS**. Dedicated model timing is enabled only by the existing private
  background-child flag, never by caller-supplied ordinary-chat metadata.
- Backend affected sweep: 737 PASS and one diagnostic test isolation failure;
  the asynchronous queue still held a prior fixture's identically named capture.
  The test now drains prior records before installing its capture sink. Final
  affected rerun: **121 PASS** (recognition, synthesis and profiling). The earlier 860-test sweep also exposed a
  media-only assertion applying to new unbound selector spans and a 20 ms
  wall-time test expiring in thread startup; those fixtures were corrected
  without changing VAD, product deadlines, retries or fallback assertions.
- Full Registry comparison against a detached pristine baseline: **158 PASS,
  61 FAIL in each checkout, identical failing test names**. This records no new
  Registry failures, not Registry acceptance. For example,
  `test_native_available_result_uses_toolless_agent_delegate` expects
  `background.query` and gets `dialogue` on both versions. The full suite's
  inherited failures remain outside this passive packet.
- `npm run build:live-voice`: PASS (TypeScript + Vite; existing large-chunk
  warning). The build is an asset verification, not a running deployment.
- Offline smoke used actual diagnostic hooks with synthetic model/tool/HTTP
  inputs: 17 records, 7 spans, 2 failure records. HTML script/DOM execution,
  stage filtering and failure-only view PASS in jsdom. Private exception sentinel
  absent from exported report. This is not a real Provider or physical rehearsal.
- Recorder-only paced smoke, 250 empty async calls and a local file log handler:
  P50 0.1604 ms, P95 0.2609 ms, max 1.0778 ms; zero dropped records. This is an
  instrumentation sanity check, not an application overhead guarantee. Fast
  unpaced test floods did hit the 256-record queue, and loss is exposed rather
  than hidden. Root logging handlers, storage and real workloads can cost more.

Commands / reproducible selection:

```powershell
$taskFiles = rg --files tests/unit_tests | Where-Object { $_ -match 'test_(demo_profiling|formal_model_diagnostics|formal_live_voice_adapter|speech_socket_diagnostics|speech_precision_diagnostics|audio_diagnostics|openai_streaming_speech|batch_speech|streaming_speech_route|dedicated_media_registration|speech_lifecycle|agent_bridge_runtime|product_streaming_synthesis|streaming_synthesis_route|project_code_executor|semantic_continuity|task_semantics|agent_client)\.py$' }
.\.venv\Scripts\python.exe -X utf8 -m pytest @taskFiles -q -o addopts='' -o log_cli=false --disable-warnings --tb=short
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/unit_tests/live_voice/test_product_composition_registry.py -q -o addopts='' -o log_cli=false --disable-warnings --tb=no
```

Frontend commands, run from its package directory:
`npm run test:live-voice-audio-diagnostics`,
`npm run test:live-voice-browser-audio-io`, `npm run build:live-voice`.

Raw local outputs are retained under ignored `logs/live-voice-profile-*`.
The detached baseline comparison uses the same interpreter/dependencies; no
branch rewrite or remote update was performed. Browser journal limits are
4,096 stored + 2,048 memory records before deduplication; hard process/tab exits
and blocked/full storage cannot guarantee tail recovery. Imports cap file/line
sizes and 200,000 records; HTML limits visible rows and keeps complete imported
records in JSON. Missing evidence is not a proof of absent side effects.

### Closure

Cold complete-diff review, scoped Markdown file links, Ruff checks for diagnostic
modules and `git diff --check` pass. Independent background-model review found
one P2: a snapshot merged with the closing task's context could add foreign-only
Session/operation IDs. Fixed with an explicit no-inheritance recorder path for
snapshot events and stream result details; the actual sink is tested to contain
only the origin's fields. Related diagnostic/model/sink tests: **32 PASS**.
Independent fix verification confirms the P2 is fixed and default inheritance /
generator cleanup remain intact. The completed `codex review --uncommitted`
review identified four additional P2s, all addressed:

- Shared unary Agent RPC timings now require an active Live Voice profile
  context, excluding unrelated heartbeat/cron/ordinary traffic. Dedicated
  background model timing additionally requires a Live Voice Task context.
- Registry rejection breadcrumbs unwrap the known `P3RouteResult.payload.error`
  carrier; only stable code/reason are copied, never message/details.
- Browser negative RPC responses have passive WeakSet provenance, preserving
  `rejected` plus stable reason/code separately from transport failure/timeout.
- Offline failure classification includes failed capture/playout status and
  fallback milestones. Ordinary active / cleanup-in-progress states stay out.

Post-review diagnostic/model/sink/Gateway tests: **61 PASS**. Frontend diagnostic
suite and complete build were rerun. A bounded independent verification of the
four fixes confirms all four resolved, with no remaining actionable regressions.
The earlier context fix also has an independent clean verification. Reviews did
not find a business-path change; this closes the scoped instrumentation batch,
not the whole product or physical acceptance.
No service manifest exists in this workspace. No real Provider invocation,
physical microphone/speaker journey, redeployment or remote push is claimed.
Prior segmentation/interruption/result defects and whole-project acceptance
remain PARTIAL; this packet supplies their diagnostic evidence path.

