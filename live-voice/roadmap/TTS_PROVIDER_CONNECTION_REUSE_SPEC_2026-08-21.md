# TTS Provider Connection Reuse Specification

> **Status:** proposed design, approved in chat on 2026-08-21; implementation
> not started.
>
> **Reference source:**
> planning base `1f2ac7ba4ef2ed6a4aee498d0d285a7f40a25403`. The exact A
> reference will be the later benchmark-seam commit derived from this base,
> before connection-reuse product behavior changes.
>
> **Boundary:** no-Chrome, real-Provider P1/P2 Speech Synthesis component.
> This document grants no implementation, performance, physical Browser,
> audible-output, network-generalization or product-acceptance credit.

## 1. Objective

Measure whether recreating the OpenAI streaming-TTS HTTP client for every
synthesis materially delays first PCM, then accept or reject one provider-owned
connection-reuse candidate through an exact A1/B/A2 loop.

The optimization target is:

```text
TTS request
→ TCP/TLS if required
→ response headers / SSE transport open
→ first Provider SSE audio event
→ first canonical PCM
```

It does not target Agent generation, Task routing, Browser downlink, WebAudio,
successor-capture readiness, playout receipt settlement, batch Speech or VAD.

## 2. Current source fact

`StreamingSynthesisRouteOwner` caches one selected
`OpenAIStreamingSpeechProvider` and closes it through a bounded, idempotent
provider-cleanup owner. The Provider can therefore own reusable transport state
for multiple exact synthesis streams.

The default synthesis transport does not currently use that lifecycle:

- `_default_sse_factory()` constructs a new `httpx.AsyncClient` for every TTS
  request;
- `_HttpxSseStream.aclose()` closes both the response and that client;
- the next TTS request must allocate a fresh application pool and cannot reuse
  its prior TCP/TLS connection.

The configured local dependency boundary is HTTPX 0.28.1 / HTTPCore 1.0.9.
HTTPCore exposes per-request content-free trace event names for TCP connect,
TLS, request headers and response headers. Product correctness must not depend
on this diagnostic extension.

## 3. Accepted approach

### 3.1 Provider-owned lazy client

`OpenAIStreamingSpeechProvider` owns at most one default synthesis
`httpx.AsyncClient` per Provider instance/event loop. The client is created
only by the first real TTS request. No startup probe, dummy phrase, HEAD/GET or
other artificial Provider request is allowed.

The default pool is bounded to:

- `max_connections = 8`, matching the current synthesis-owner active-stream
  bound;
- `max_keepalive_connections = 8`;
- `keepalive_expiry = 30.0` seconds;
- redirects disabled and no whole-client timeout, preserving the existing
  per-connect and per-event budgets.

Request Authorization, model, voice and text remain request-local. They are not
stored as client default headers or represented by the pool.

### 3.2 Stream and client cleanup

Each synthesis stream owns one HTTP response and closes only that response.
Closing/cancelling one response cannot close the shared client or another
response.

`OpenAIStreamingSpeechProvider.close()` owns the shared client cleanup after it
has fenced new sessions, closed active responses and settled synthesis workers.
Client close uses the existing `_TransportCleanupOwner` so that:

- callers remain hard-bounded;
- a cancellation-hostile or failed close is retained truthfully;
- an incomplete close consumes bounded cleanup capacity and makes final
  Provider cleanup fail closed;
- a later exact close retries the same resource rather than allocating or
  claiming a new pool;
- close is idempotent and process-control exceptions remain preserved.

The client reference is cleared only after confirmed cleanup. A Provider whose
close began never reopens a pool.

### 3.3 Concurrency and failure

Client creation and close are linearized by one Provider-local async lifecycle
lock. Concurrent synthesis streams may share the bounded pool, but each retains
its existing response/generation, timeout, event queue, cancel and conformance
ownership.

HTTPX/HTTPCore decides whether a pooled connection is reusable. A broken or
server-closed connection is discarded by the transport. Product code adds no
request retry, replay or fallback. The existing streaming-route owner remains
the only authority for fallback eligibility.

Feature-off, invalid configuration and an injected custom `sse_factory` create
zero default HTTP clients. Existing test factories remain explicitly owned by
their tests and are never silently wrapped in the product pool.

## 4. Rejected approaches

### 4.1 Process-global HTTP client

Rejected because it would mix configuration, event loops, close authority and
future tenant/provider boundaries. A global client could outlive the Gateway
owner that is responsible for cleanup.

### 4.2 Artificial prewarm request

Rejected because OpenAI-compatible deployments do not guarantee a safe
connection-only endpoint. A dummy synthesis or unrelated authenticated request
adds billing, rate-limit, audit and Provider-side effects. Natural first-use
warming plus later reuse is sufficient for this experiment.

### 4.3 Gateway-owned generic transport pool

Deferred as unnecessary abstraction. The existing Provider lifetime already
matches the resource. Moving ownership into Gateway composition would widen
interfaces without improving this measurement.

## 5. Diagnostic timing seam

The default SSE path may receive one optional content-free trace observer for
the benchmark. It observes only the exact `SynthesisStreamRef`, a closed
event-name union and a monotonic timestamp:

```text
connect_tcp.started
connect_tcp.complete
start_tls.started
start_tls.complete
send_request_headers.started
receive_response_headers.complete
first_audio_event
```

The adapter discards HTTPCore trace payloads, return values and exception
objects. It normalizes only the listed suffixes from HTTP/1.1 or HTTP/2 trace
names. Unknown events are ignored. Observer exceptions are contained and cannot
change the Provider request or cleanup. `first_audio_event` is emitted once
when the first valid SSE audio delta is accepted, before local PCM resampling.

Runtime with no observer performs no diagnostic serialization, logging or
report write. The product does not use trace events to decide success, retry,
fallback or connection reuse.

Connection reuse is reported only when a successful request has no TCP/TLS
start event while the same Provider-owned client remains live. Missing trace
support or an incomplete trace makes the attempt `invalid`; absence alone never
becomes a guessed reuse claim.

## 6. Real-Provider benchmark

### 6.1 Runner and source discipline

The runner lives under `scripts/live_voice/` and calls the real
`OpenAIStreamingSpeechProvider` directly. It never starts JiuwenSwarm, Gateway,
Agent, Chrome, microphone, speaker or WebAudio.

Every credited run requires:

- exact clean Git source and supplied 40-character commit;
- Python, HTTPX and HTTPCore version labels;
- the same configured Provider, model, voice, short fixed English input and
  24 kHz output across A1/B/A2;
- sequential execution with no benchmark-owned retry;
- private exclusive report creation with mode `0600`.

Credentials and API base remain environment-only. The report contains no API
key, URL, request/response headers, text, PCM, SSE payload, Provider exception,
ticket, device or user/session identity.

### 6.2 Population

Each source runs three independent pairs. Each pair creates a new Provider:

1. `cold`: the first synthesis on that Provider/client;
2. `warm`: an immediate second synthesis on the same Provider;
3. close the Provider and require a clean cleanup snapshot before the next
   pair.

Before formal A1, one uncredited A-reference pilot pair verifies credentials,
closed trace support, report shape and cleanup. A1, B and A2 then use six paid
short syntheses each, eighteen credited calls and twenty real Provider calls
including the pilot. A1 and A2 use the exact same unchanged reference commit.
B contains only the connection-reuse candidate plus benchmark seams already
present in the A reference.

“Cold” means a fresh application HTTP client. It does not claim an empty OS DNS
cache, TCP stack or TLS session cache. A1/A2 return control and within-pair
comparison bound those machine effects.

### 6.3 Attempt schema

The closed report schema is
`live-voice.tts-provider-connection-causal-report.v0`. Each attempt contains:

```text
pair_index
position = cold | warm
outcome = completed | failed | invalid | unknown
reason = stable token | null
connection_reused = true | false | null
request_started_ms = 0
tcp_connect_started_ms | null
tcp_connect_completed_ms | null
tls_started_ms | null
tls_completed_ms | null
response_headers_ms
transport_open_ms
first_audio_event_ms
first_pcm_ms
completed_ms
stream_closed_ms
```

Numeric values are finite, non-negative monotonic offsets. Failed, invalid and
unknown attempts remain in the denominator and receive no latency-summary
credit. The report also contains per-position p50/p95, outcome counts, cleanup
counts, exact source/configuration labels and zero forbidden effects.

### 6.4 Privacy and external effects

The runner's allowed external effects are exactly one two-request pilot plus
the eighteen declared formal TTS requests and their transport cleanup. It
performs zero:

- Agent, Tool, Task, history or browser-audio effect;
- Speech recognition or VAD request;
- fallback or retry;
- report overwrite;
- transcript, prompt or PCM persistence.

CLI errors and logs expose only stable tokens. Raw reports stay outside Git.

## 7. A1/B/A2 decision

### 7.1 A1 materiality gate

A1 must complete 6/6 attempts with clean Provider cleanup. The candidate is
eligible only if every A1 attempt proves a fresh TCP connect and, for HTTPS, a
fresh TLS path under the current per-request client lifecycle. If the
Provider/network uses a path for which the closed trace cannot distinguish
connection setup, the experiment is
`INCONCLUSIVE` and product code is not changed.

### 7.2 Candidate acceptance

`TTS_PROVIDER_CONNECTION_REUSE_ACCEPTED` requires all of:

- B and both controls complete every attempt with zero failed, invalid or
  unknown outcome;
- all B warm attempts prove reuse; cold attempts prove a fresh connection;
- B warm `request → first_pcm` p50 improves by at least 100 ms and 10% against
  both A1 and A2 warm p50;
- B cold p50/p95 regress by no more than 20% against both controls;
- response-header, transport-open and first-event breakdowns show the gain was
  removed from connection setup rather than shifted after headers;
- A1 and A2 p50 differ by no more than 15% for cold and warm populations and
  have identical outcome/reuse counts;
- every pair ends with a clean transport-cleanup snapshot and zero forbidden
  effects;
- injected unit/integration faults prove close, cancel, concurrency, stale
  session and feature-off behavior independently of the paid run.

Otherwise the decision is `REJECTED` or `INCONCLUSIVE`, current product
lifecycle is retained, and the exact reason is documented.

## 8. Verification boundary

Risk is Tier 2: the change owns shared transport state, concurrency, cancel and
cleanup but does not change business authority or a public wire contract.
Applicable root `TESTING.md` dimensions are:

- P: cold and reused synthesis produce the same exact ordered TTS result;
- N/B: invalid config, malformed Provider response, pool bounds and report
  boundaries fail closed;
- S/T/C: open/close, simultaneous streams, timeout, cancellation and late
  callbacks cannot revive the client or a response;
- R: broken pooled connection has no hidden product retry and next explicit
  request follows HTTPX transport truth;
- I: Provider/config/event-loop ownership cannot cross instances;
- F: feature-off and injected factories allocate zero default pool resources;
- K: existing streaming Speech conformance and batch paths remain unchanged;
- X: real OpenAI Provider A1/B/A2 closes only the no-Chrome Provider seam.

Independent Tier-2 review is required after the implementation and real-run
evidence. Physical Browser and audible acceptance remain deferred.

## 9. Deliverables and exclusions

Deliverables:

- closed real-Provider causal runner and unit tests;
- provider-owned reusable SSE client with bounded cleanup;
- A1/B/A2 private reports and sanitized result;
- affected streaming synthesis and Provider regressions;
- Tier-2 review and current documentation synchronization.

Explicit exclusions:

- batch `OpenAICompatibleBatchSpeechProvider` connection reuse;
- proactive/dummy prewarm requests;
- STT WebSocket lifecycle;
- Agent/Task/P3 changes;
- TTS caching, sentence prefetch or model/text changes;
- Browser/WebAudio/downlink/receipt optimization;
- Production multi-tenant pooling or public SLO claims.
