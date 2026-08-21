# EOT/STT Settlement Overlap — Causal Benchmark and Candidate Specification

Date: 2026-08-21

> **Priority note:** after current-code and Hongxing-commit reconciliation,
> this remains a valid measurement-first packet but is conditional rather than
> the next presumed large optimization. TTS/capture reconciliation and the
> no-Chrome TTS first-audio A1 precede it. See the
> [non-Agent P1/P2/P3 brainstorm](NON_AGENT_P1_P2_P3_LATENCY_OPTIMIZATION_BRAINSTORM_2026-08-21.md).

> **Closed-result note:** complete A1 source `8e5dab8b8` retained all ten marks
> and eight segments in 20/20 exact cleanup-complete attempts. The largest
> respective removable-gap/fraction p50 values were 0.880 ms and 0.015, so the decision is
> `NO_MATERIAL_SERIAL_GAP`; no product candidate is permitted. The next latency
> screen is Provider-native Semantic VAD with the 1200 ms fallback retained.

## 1. Goal and decision boundary

Determine whether starting the exact streaming-result waiter before local
uplink settlement measurably reduces `EOT → recognized final` latency, then
implement that join only if a candidate-neutral A1 proves a material serial
wait exists.

This packet is measurement-first. It does not assume the proposed overlap is
useful merely because the current Browser method is written sequentially.
Current Gateway code already collects Provider events while media is flowing;
the residual candidate can overlap only Browser/Gateway result-request work
with local drain, ACK and close.

The decision is one of:

- `NO_MATERIAL_SERIAL_GAP`: A1 shows less than 80 ms p50 removable wait or less
  than 10% of `EOT → recognized final`; do not change the product protocol and
  route next to the separately specified Provider-native Semantic VAD screen.
- `JOIN_CANDIDATE_ELIGIBLE`: A1 proves a material gap and all safety fixtures
  are measurable; implement B and run unchanged-source A2.
- `JOIN_CANDIDATE_ACCEPTED`: B improves both A1 and A2 without moving the wait,
  weakening settlement or introducing forbidden effects.
- `JOIN_CANDIDATE_REJECTED`: B is neutral, unstable or violates any gate.
- `INCONCLUSIVE`: runner, timing, cleanup or reference instability prevents a
  causal decision.

## 2. Capability, risk and authority

- Capability owners: P1 Speech Recognition, P2 Realtime Media and Conversation
  Runtime product composition.
- Risk: Tier 2 for state/order/cancel/recovery, promoted to Tier 3 if the shared
  wire method or authority semantics must change incompatibly.
- A partial/final transcript never authorizes Agent, Tool or Task. Only the
  existing committed product owner may submit recognized text.
- Media ACK proves accepted uplink frames; it does not itself prove a valid STT
  final. A Provider final does not prove local frame settlement.
- The product may expose text only after both independent facts succeed.
- `ServerVadConfig.silence_duration_ms=1200` remains unchanged.

The stable Commit, Media, Speech/Interaction, Identity, Fence and Error
contracts in `architecture/FULL_SOLUTION_2026-07-30.md` §§2, 4–5 remain
authoritative through current `STATUS.md`.

## 3. Explicit no-Chrome boundary

This packet requires no Chrome, browser process, microphone, speaker, WebAudio
or device permissions. TypeScript Browser-owner code may be changed, but it is
executed under the existing Node test harness with deterministic Audio/Media
and transport fakes.

Excluded from credit:

- physical capture, AEC/NS/AGC and device recovery;
- WebSocket/network latency claims beyond injected deterministic transport;
- TTS, downlink, WebAudio scheduling and first audible;
- Agent/model/tool execution;
- physical barge-in and perceived end-to-end latency;
- semantic/adaptive VAD and any fixed-threshold change.

## 4. Current-source facts

The formal Browser path in `productP1VoiceRoute.ts::#stopAndRecognizeOnce` is:

```text
Provider EOT control
→ stopCapture
→ drain captured frames
→ wait pending media frames/ACK
→ completeUplink and await route completion
→ call recognizeStreamingFinal
→ validate exact result
→ release captured frames
→ product submit may proceed
```

The Gateway is less serial than this surface suggests:

- `StreamingRecognitionRouteOwner` starts its event collector when recognition
  opens, before EOT.
- `SPEECH_STOPPED` fences Provider input and the collector continues toward
  `FINAL` while local media settles.
- `finish()` skips another Provider commit when the server-VAD event task is
  already final.
- `finish_streaming_recognition()` currently retains the publishable outcome
  only after the media route completes.
- `streaming_recognition_result()` currently authorizes requests only for a
  `route_completed` record.

Therefore the Provider-final retrieval itself is already concurrent. The
candidate can save result-request scheduling/transport and any residual finish
join after local settlement; it cannot legitimately claim the full VAD or
Provider-final duration as new overlap.

## 5. Alternatives

### A. Early result waiter with authoritative join — selected candidate

Start one result waiter after capture has stopped and its final in-memory frame
set is frozen, but before waiting for media drain/ACK/close. Continue local
settlement concurrently. The result remains non-publishable until both local
settlement and Provider final succeed.

Benefits: attacks the only confirmed surface serialization and preserves the
existing collector. Cost: requires an exact pre-settlement waiter authority and
careful cancellation.

### B. Gateway-only eager final cache

Retain Provider final earlier without changing Browser request order. This is
mostly present already through `event_task`; it is unlikely to remove the
Browser/RPC tail and is not the first candidate.

### C. Skip the product waiter

If A1 shows the post-settlement result wait is below the materiality threshold,
this is the required outcome. Do not implement A merely to complete a planned
feature; route next to the current latency-plan owner.

## 6. Candidate-neutral A1 benchmark

The first implementation is a benchmark/harness, not the product join.

It extends the existing `LatencyProbeRuntime`, Browser latency-round marks,
correlation identity and report reduction. It may add only the missing
result-wait start/return boundaries and a fixture-specific reducer; it must not
create a second trace/event protocol or general observability platform.

It composes the real current `ProductP1VoiceRoute` owner and Gateway registry
seams with deterministic dependencies. Fixed populations vary two independent
readiness times:

| Fixture | Local uplink settlement | Provider final readiness |
|---|---:|---:|
| local-fast/provider-fast | 50 ms | 50 ms |
| local-slow/provider-fast | 500 ms | 50 ms |
| local-fast/provider-slow | 50 ms | 500 ms |
| both-slow | 500 ms | 500 ms |

Each fixture runs at least five attempts. A1 records:

- `browser.eot_received`;
- `browser.capture_stop_requested`;
- `browser.capture_stopped`;
- `browser.uplink_last_frame_sent`;
- `browser.uplink_last_ack_received`;
- `browser.uplink_closed`;
- `benchmark.provider_final_ready`;
- `browser.streaming_result_request_started`;
- `browser.streaming_result_returned`;
- `browser.stt_final_received`.

Derived segments:

- EOT → capture stopped;
- capture stopped → last ACK;
- last ACK → route settled;
- EOT → Provider final ready;
- route settled → result request started;
- result request started → result returned;
- route settled → result returned;
- EOT → recognized final accepted.

The benchmark also records RPC count and exact outcome, but no transcript,
audio payload or private exception text. The fixed synthetic registry business
envelope may cross only captured in-memory child stdout because the real
Product P1 owner must consume it. Reports, error strings and terminal output
remain content-free.

Materiality gate: the candidate proceeds only when the removable serial gap
`streaming result returned − max(uplink closed, Provider final ready)` has p50
at least 80 ms and its fraction of `EOT → recognized final` has p50 at least
10% in one or more declared fixtures, with A1 pacing and cleanup valid.
`route settled → result returned` is diagnostic only: it can include legitimate
remaining Provider-final wait and cannot authorize the candidate.

## 7. B candidate data flow

When both server and Web feature flags/capability agree:

1. EOT triggers the existing single `stopAndRecognize()` owner.
2. Browser stops capture and drains all callbacks into its immutable frame set.
3. Browser creates an AbortController bound to the exact operation generation.
4. Browser starts one early streaming-result waiter using exact session,
   correlation, interaction, capture generation and track identity.
5. Browser concurrently drains the media sender, waits the exact last ACK and
   completes the uplink route.
6. Gateway may retain Provider final before local settlement, but cannot return
   or authorize fallback from the early waiter yet.
7. Route completion establishes accepted-frame count, content hash and current
   product activation.
8. The Gateway join returns only when route settlement and the matching
   Provider outcome both succeed.
9. Browser validates the unchanged final envelope, generation and capture,
   then allows the ordinary product owner to submit.

The join is `max(local settlement, Provider final/result readiness)`, never
`first one wins`.

## 8. Protocol and compatibility shape

Prefer a separate early-wait operation rather than weakening the existing
closed `live_voice.speech.recognize_streaming_result` authorization. The exact
name and wire record are frozen in the implementation plan after source/test
enumeration, but must satisfy:

- closed params with existing exact identity plus one literal protocol version;
- default-off server registration/advertisement;
- no early response, fallback or text on an unsettled route;
- one retained request identity; identical retry receives the same outcome;
- changed identity or concurrent foreign waiter conflicts before effects;
- the legacy result method and legacy Web flow remain byte/behaviour compatible
  while either flag is off.

The Web flag is independent from the existing P2 notification batch and VAD
benchmark flags. The server capability must be observed before the Web owner
uses the new operation.

## 9. Failure and cancellation semantics

- Local drain, ACK or route-close failure aborts the early waiter and exact
  Provider stream. No result/fallback/submit is accepted.
- Provider failure or timeout is retained but cannot authorize batch fallback
  until local route settlement succeeds.
- If local settlement later succeeds, the existing declared fallback policy may
  run once under the same capture identity.
- Stale activation, capture generation, track, connection epoch or origin
  rejects before returning text.
- Caller cancel, disconnect, Exit or product generation change aborts both
  branches and settles retained tasks under existing bounds.
- A late successful predecessor result is fenced and cannot revive the turn.
- Process-control exceptions are cleaned up and rethrown without private text.

## 10. A1/B/A2 acceptance

If A1 passes the materiality gate:

- A1: exact clean reference, early join disabled;
- B: one named candidate commit, early join enabled;
- A2: exact unchanged A1 source and fixtures;
- identical injected delays, attempt count and machine;
- p50 and nearest-rank p95 per segment;
- no comparison against historical Browser numbers.

B is accepted only when:

- EOT → recognized final p50 improves by at least 80 ms and 10% against both
  A1 and A2 in each fixture where A1 proved a serial gap;
- no p95 regression greater than 20 ms in any other declared segment;
- exact recognized final and ordering remain identical;
- local settlement, Provider final, timeout and cleanup are truthful for every
  attempt;
- forbidden Agent, Tool, Task, history, TTS, audio-downlink and product-submit
  counters remain zero inside the causal runner;
- the complete applicable Tier-2 P/N/B/S/T/C/R/I/F/K/X matrix and independent
  review close.

If A1 does not pass materiality, record `NO_MATERIAL_SERIAL_GAP`, commit no
product candidate and route TTS first-audio as the next optimization owner.

## 11. Planned ownership

Expected affected boundaries after the implementation plan is approved:

- `productP1VoiceRoute.ts` and its owner tests;
- `gatewayBatchSpeechClient.ts` and protocol/parser tests;
- `dedicated_media_registration.py` and focused registry tests;
- Web dispatch allowlist only if a new method is selected;
- one no-Chrome causal runner and report test;
- scoped evidence/STATUS/latency-plan synchronization after A1 or A1/B/A2.

Product Provider adapters, VAD defaults, Agent-Core, TTS, WebAudio and physical
runbooks are excluded unless a RED proves an unavoidable owning dependency and
the scope is re-approved.

## 12. Completion boundary

Completion means one of two honest outcomes:

1. A1 proves no material serial gap and the packet closes without product
   changes; or
2. A1/B/A2 accepts or rejects one exact early-join candidate with deterministic
   no-Chrome evidence and independent Tier-2 review.

Neither outcome grants Browser, device, first-audible, end-to-end,
product-readiness or Production credit.
