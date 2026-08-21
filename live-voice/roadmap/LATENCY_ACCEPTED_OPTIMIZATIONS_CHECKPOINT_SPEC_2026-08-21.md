# Accepted Optimizations Latency Checkpoint Specification

> **Status:** proposed architecture, approved section-by-section in chat on
> 2026-08-21; implementation not started.
>
> **Planning branch:** `latency_checkpoint_accepted_optimizations`.
>
> **Planning base:** `5b87a59927f866c9a63c0bb774e4a9e2650628b9`.
>
> **Boundary:** default-off, no-Chrome deterministic P1/P2 checkpoint plus a
> separately labelled exploratory manual-Web measurement lane. This document
> grants no implementation, run, physical Browser, Provider, Agent/model,
> audible-output, product-readiness or Production credit.

## 1. Objective

Create one reproducible checkpoint that measures the combined effect of every
currently accepted non-Agent Live Voice latency optimization on the same
complete controlled round:

```text
speech end
→ STT final
→ authoritative admission
→ deterministic Agent/model completion
→ P2 final consumed
→ TTS ready
→ first source
→ playout complete
→ confirmed Presentation ACK and next-turn readiness
```

The primary result is the absolute monotonic duration:

```text
speech end → confirmed playout ACK / next-turn ready
```

The checkpoint must report stage p50/p95 and total p50/p95 in milliseconds for
an exact A1/B/A2 sequence. Percentages are secondary derived fields. Existing
component percentages must never be added or presented as end-to-end gain.

The same packet also adds a default-off manual Web lane so a developer can arm
one real UI voice turn, speak normally and view/download truthful timings. The
manual lane is exploratory and cannot enter the deterministic A1/B/A2
population.

## 2. Accepted optimization set

B contains exactly these accepted product behaviors:

1. **P2 bounded notification pull** — up to 16 ordered notifications per RPC,
   stopping at authoritative final/error/Tool/Task/Presentation barriers;
2. **TTS successor-ACK decoupling** — TTS downlink/playout may begin while
   successor-capture readiness is pending, while confirmed receipt remains
   gated by the exact successful settlement conditions.

The current source already contains both accepted behaviors. Their owner-scoped
evidence remains:

- [P2 bounded-pull causal result](../evidence/P2_NOTIFICATION_BOUNDED_PULL_CAUSAL_RESULT_2026-08-21.md);
- [TTS first-audio causal result](../evidence/TTS_FIRST_AUDIO_CAUSAL_RESULT_2026-08-21.md).

The checkpoint does not reconsider those component decisions. It asks how much
their composition changes one controlled full-round total.

Explicitly excluded from B:

- fixed VAD 900/800 ms, rejected for early EOT;
- application-level TTS HTTP client reuse, rejected after 0/3 warm connections
  reused and a 7.0% p50 regression;
- unaccepted EOT/STT overlap, semantic/adaptive VAD, sentence streaming,
  acknowledgement caching or post-`audio.done` EOF draining;
- Agent-Core/model/Tool optimization;
- Browser/device/WebAudio physical optimization.

## 3. Measurement truth taxonomy

Every numeric field, table and prose claim must carry one of these truth
classes. A value cannot silently change class in summaries.

### 3.1 `MEASURED`

Observed directly from two events on one monotonic clock during one attempt.

Deterministic lane `MEASURED` values:

- every stage start/end observation;
- `speech_end → confirmed_ack` total;
- P2 RPC count and time spent consuming the final sequence;
- successor ACK observed time;
- downlink open, first frame/source, playout complete and confirmed ACK times;
- A1/B/A2 p50/p95 calculated from valid measured attempt durations.

Manual Web `MEASURED` values:

- `capture_armed → confirmed_ack`;
- `browser.eot_received → confirmed_ack`;
- exact Browser-clock sub-stages whose marks both exist;
- Gateway/Agent drill-downs only within their own monotonic domains.

No arithmetic may subtract clocks from different processes.

### 3.2 `CONTROLLED`

A configured fixture delay or workload fact that the runner injects and then
checks against observed timing. It is not a real Provider/model measurement.

Controlled facts include:

- STT settlement target: 400 ms;
- admission target: 500 ms;
- Agent/model target: 2,000 ms;
- W3 Tool interval target: 1,000 ms;
- TTS generation target: 1,000 ms;
- P2 per-RPC transport delay: 85 ms;
- successor ACK delay: 250 or 750 ms;
- deterministic PCM playout duration: 3,000, 6,000 or 4,000 ms;
- notification count/order/barrier positions and B batch bound 16.

Reports contain both configured targets and observed `MEASURED` durations.
Deviation beyond the closed scheduler tolerance invalidates the attempt; the
configured target never replaces the observation. For positive waits, the
closed tolerance is `max(25 ms, 5% of target)`; early completion below the
configured target is always invalid.

### 3.3 `DERIVED`

Calculated only from compatible facts in the same closed report:

- B minus A1 and B minus A2 absolute millisecond deltas;
- percentage delta using the same stage/workload/population;
- A1/A2 drift;
- each B stage's share of B total;
- successful/failure/unknown rates.

Derived totals are not the sum of independently rounded percentiles. The
runner measures each attempt's total first, then summarizes the total
population.

### 3.4 `ESTIMATED`

A projection or hypothesis based on prior evidence, source inspection or the
manual speech-end estimator. It receives no A1/B/A2 credit.

Estimated values include:

- possible gain from semantic/adaptive VAD;
- possible EOT/STT settlement overlap;
- possible post-`audio.done` EOF/connection reuse;
- possible sentence-level Agent→TTS overlap;
- historical physical/real-Agent ranges used to discuss future headroom;
- manual `estimated_last_voiced_frame → confirmed_ack` and its uncertainty.

Every estimate must cite its evidence and remain in a separate table from
measured checkpoint results.

### 3.5 `OUT_OF_SCOPE`

Not exercised and not numerically claimed by the deterministic checkpoint:

- microphone/device capture;
- real Provider STT/TTS latency and network behavior;
- real Agent/model/Tool execution;
- physical Chrome/WebAudio scheduling and human first-audible time;
- real acoustic VAD quality, echo, interruption or underrun.

## 4. Deterministic workload matrix

All prompts and outputs are public fixed fixtures. A1, B and A2 use identical
fixture bytes, non-optimization timing configuration and runner source. Their
closed optimization mode differs only as specified in section 5.

| ID | Type | Fixed recognized prompt | P2 sequence | Successor ACK | PCM playout |
|---|---|---|---:|---:|---:|
| W1 | short dialogue, no Tool | `In two short sentences, please introduce Paris.` | 9 ordered observation deltas, then `chat.final` | 250 ms | 3,000 ms |
| W2 | long dialogue, no Tool | `Plan a three-day itinerary for Paris with morning, afternoon, and evening activities.` | 49 ordered observation deltas, then `chat.final` | 750 ms | 6,000 ms |
| W3 | deterministic Tool-style result | `What is the weather today in Paris, and should I carry an umbrella?` | 99 ordered observations with exact Tool barriers, then `chat.final` | 750 ms | 4,000 ms |

W3's 100-item sequence is exact:

```text
publish_seq 0..39   = non-authoritative chat.delta/reasoning observations
publish_seq 40      = tool_execution_started barrier
controlled wait     = 1,000 ms
publish_seq 41      = tool_execution_completed barrier
publish_seq 42..98  = ordered non-authoritative observations
publish_seq 99      = exact chat.final + PresentationUnit
```

The 1,000 ms Tool interval occurs inside W3's controlled Agent/model schedule.
P2 consumption begins only after the full exact sequence is queued and
`model_complete` is marked, so A and B receive the same backlog. The barriers
still force separate bounded pulls during consumption.

Bounded pull must include each barrier as its batch tail and resume only through
the next explicit RPC. It may not batch across Tool authority.

Common controlled stages:

| Stage | Target |
|---|---:|
| speech end → STT final | 400 ms |
| STT final → authoritative admission | 500 ms |
| admission → deterministic Agent/model complete | 2,000 ms |
| model complete → P2 final consumed | measured from real P2 owner; 85 ms per transport RPC |
| final consumed → TTS ready | 1,000 ms |
| PCM playout | W1 3,000 / W2 6,000 / W3 4,000 ms |

The Agent/model fixture enqueues the complete declared notification sequence at
its `model_complete` boundary. This intentionally reproduces the accepted P2
backlog question instead of pretending to measure progressive real-model
streaming.

## 5. A1/B/A2 source construction

### 5.1 Neutral runner commit

The first implementation commit contains only:

- closed checkpoint schema and deterministic scheduler;
- real P2/P1 owner composition;
- default-off manual Web diagnostics;
- tests, CLI and private report writer.

It does not change either accepted optimization. Its runner/config hashes are
identical in A1, B and A2.

### 5.2 B optimized source

B is the checkpoint branch with both accepted behaviors enabled. The exact
commit is frozen only after implementation, cumulative verification and Tier-3
review.

### 5.3 A reference source and optimization modes

P2 already has a truthful feature-off baseline in the accepted source. A does
not reverse the 14-file P2 implementation. It uses the same P2 code with:

```text
server P2 notification batch flag = false
Web notification_batch_size       = 1
```

B uses:

```text
server P2 notification batch flag = true
Web notification_batch_size       = 16
```

TTS successor-ACK decoupling has no equivalent runtime switch. A is derived
from the neutral-runner source by reverse-applying only the accepted TTS
product behavior in:

```text
jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts
jiuwenswarm/gateway/live_voice/dedicated_media_registration.py
```

Tests and causal runners are not reverse-applied. The A diff must reproduce the
old sequential rule—successor ACK before downlink—without changing any unrelated
current behavior. A1 and A2 use the exact same 40-character commit. B uses the
exact neutral-runner/optimized commit.

The comparer accepts only these declared A/B differences:

- P2 batch flag and canonical batch size 1 versus 16;
- TTS sequential reference source versus accepted overlap source;
- run/population/source identifiers.

Every fixture, delay, workload, sample count, privacy rule, runner hash and
non-optimization configuration must match.

### 5.4 Population

Run order:

```text
A1: W1/W2/W3 × 5 attempts
B:  W1/W2/W3 × 5 attempts
A2: W1/W2/W3 × 5 attempts
```

Total: 45 deterministic attempts. Attempts are sequential within one
population; no benchmark-owned retry is allowed.

## 6. Deterministic event graph and timings

One attempt follows this graph on one monotonic clock:

```text
D0 speech_end
  → controlled STT wait
D1 stt_final
  → controlled admission wait
D2 admission_accepted
  → controlled Agent/model wait (+ W3 Tool wait at its exact barrier)
D3 model_complete_and_notifications_enqueued
  → real ProductWebP2ActivationOwner consumes the exact sequence
D4 presentation_final_consumed
  → controlled TTS generation wait
D5 tts_ready_and_successor_capture_requested
  ├─ successor ACK timer
  └─ A waits for ACK before downlink; B opens downlink concurrently
D6 downlink_opened
D7 first_frame_received
D8 first_source_scheduled
  → controlled fixed PCM playout
D9 playout_completed
  → exact Product P1/P2 settlement join
D10 confirmed_ack_and_next_turn_ready
```

Required measured segments:

```text
stt_settlement             = D0 → D1
admission                  = D1 → D2
agent_model                = D2 → D3
p2_final_delivery          = D3 → D4
tts_generation             = D4 → D5
tts_ready_to_downlink      = D5 → D6
downlink_to_first_source   = D6 → D8
first_source_to_playout    = D8 → D9
playout_to_confirmed_ack   = D9 → D10
round_total                = D0 → D10
```

The runner records event timestamps and direct segment durations. It does not
derive `round_total` by adding summarized stages.

## 7. Closed report and English checkpoint update

Raw schema name:

```text
live-voice.accepted-optimizations-checkpoint.v0
```

Every raw report is exclusive-created, mode `0600`, outside Git and contains:

- exact source/runner/config fingerprints;
- truth class for every field;
- workload, population and attempt identity;
- configured controlled targets;
- observed monotonic event offsets and direct stage/total durations;
- P2 RPC/batch counts, ordered barrier facts and outcome;
- exact product completion/ACK/next-turn status;
- zero forbidden-effect counters;
- per-workload p50/p95 and outcome counts.

It contains no credential, endpoint, transcript from a user, PCM, private
Provider payload, exception text, Session/project path or user identity.

The sanitized English evidence file is:

```text
live-voice/evidence/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_2026-08-21.md
```

Its main table is:

| Stage | A1 p50/p95 | B p50/p95 | A2 p50/p95 | B−A1 ms | B−A2 ms | Truth |
|---|---:|---:|---:|---:|---:|---|

The report provides `round_total` in absolute milliseconds for W1/W2/W3, then
explains percentage changes. It contains separate sections for:

1. measured combined improvement;
2. B residual milliseconds and share of total;
3. proven removable headroom;
4. estimated/hypothesis headroom;
5. controlled fixture time and out-of-scope real systems.

## 8. Headroom rules

### 8.1 Measured residual

For each workload, rank B stage p50 by absolute milliseconds and show its share
of measured B `round_total`. This answers where time remains in the controlled
pipeline.

### 8.2 Proven removable headroom

Only the compatible A1/B/A2 absolute delta for the two accepted behaviors is
proven removable in this checkpoint. A component's old percentage cannot be
substituted for the combined delta.

### 8.3 Estimated future headroom

Historical evidence may rank hypotheses, but each row is labelled `ESTIMATED`
and includes confidence/risk:

- EOT/STT settlement overlap;
- semantic/adaptive VAD with 1,200 ms fallback;
- post-`audio.done` EOF draining;
- sentence-level Agent→TTS overlap;
- bounded authoritative acknowledgement;
- physical WebAudio/device startup.

The checkpoint must not add estimates to its measured total or promise an
optimized future total.

## 9. Manual Web UI lane

### 9.1 User flow

The developer starts JiuwenSwarm normally and opens a generated saved-chat URL
in their own Browser. No automatic Chrome launch is required.

With `VITE_FEATURE_LIVE_VOICE_LATENCY_CHECKPOINT=true`, a small diagnostic panel
shows:

```text
Idle → Arm next turn → Listening → Response/Playout → Settled | Failed
```

One `Arm next turn` owns exactly one admitted voice turn. After exact confirmed
ACK, the panel displays stage milliseconds and offers JSON/Markdown download.
`Repeat` creates a new attempt identity; it cannot reuse or overwrite the prior
attempt.

### 9.2 Manual totals

Exact `MEASURED` Browser totals:

- `capture_armed → confirmed_ack`;
- `browser.eot_received → confirmed_ack`.

Exploratory `ESTIMATED` total:

- `estimated_last_voiced_frame → confirmed_ack`.

The local capture processor may emit a content-free last-voiced-frame estimate
using a closed RMS/quantum rule. It records no samples and reports the threshold,
sample rate, quantum and uncertainty. Noise, echo or local processing can move
the estimate; the UI and report must visibly label it `ESTIMATED`.

### 9.3 Isolation

Manual results use lane `manual_web_exploratory`. They cannot be loaded by the
deterministic A1/B/A2 comparer. Prompt/audio/device/Agent/Provider variation
stays in the denominator and is never averaged with controlled workloads.

Feature-off, unarmed, wrong Session, stale activation and malformed result paths
produce zero checkpoint write and zero new Agent/Tool/Task/audio/history effect.

## 10. Acceptance gates

The deterministic checkpoint is complete only if:

- A1/B/A2 runner and fixture/timing hashes are identical; their optimization
  mode fingerprints differ only by the closed fields allowed in section 5.3;
- A1 and A2 use the exact same TTS-reference source commit; B uses the exact
  accepted-overlap source commit;
- all three populations complete 15/15 attempts;
- every workload has five numeric `round_total` samples;
- A1/A2 total and target-stage p50 drift is at most 10%;
- B preserves exact notification order/barriers, PresentationUnit, playout ACK
  and next-turn readiness;
- B has the exact 1/4/8 P2 RPC shape for W1/W2/W3; W3's eight requests follow
  the closed 16-item bound plus mandatory Tool-start, Tool-complete and final
  barriers;
- no failure, unknown, fallback, underrun, rebuffer, retry or forbidden effect
  is hidden;
- raw reports reparse deeply and remain mode `0600`;
- the English result distinguishes every `MEASURED`, `CONTROLLED`, `DERIVED`,
  `ESTIMATED` and `OUT_OF_SCOPE` claim.

The checkpoint records `IMPROVED`, `REGRESSED` or `INCONCLUSIVE` per workload
and overall. It does not re-accept the individual candidates or grant product
latency acceptance.

The manual Web lane is complete when feature-off and fault tests pass and one
developer can arm, settle and download an exact turn. A manual run is never a
gate for deterministic checkpoint validity.

## 11. Risk, verification and review

Risk is Tier 3 because the diagnostic composition crosses Browser/P1/P2 owner
boundaries, even though it is default-off and must not acquire product
authority.

Applicable root `TESTING.md` dimensions include:

- P: exact W1/W2/W3 A/B completion and manual arm/settle;
- N/B: malformed config/report, bounds, barrier and file privacy;
- S/T/C: repeated attempts, stale activation, close, delayed ACK and races;
- R: identical retry/replay behavior and no benchmark retry;
- I: exact source/run/Session/workload/attempt ownership;
- F: feature-off and unarmed paths with zero diagnostic/product effects;
- K: existing P2/TTS/component, Integrated Web and text-path regressions;
- X: real owner composition at deterministic scope and one exploratory manual
  UI flow, without physical acceptance.

Required verification:

- TDD RED/GREEN for schema, scheduler, P2/TTS composition and manual UI;
- focused backend/frontend tests and production frontend build;
- exact A/B source/diff and runner-hash audit;
- independent Tier-3 code review before A1/B/A2;
- independent evidence review after reports are written;
- Markdown link, Ruff/type/compile/format and diff checks.

## 12. Deliverables and exclusions

Deliverables:

- neutral deterministic checkpoint runner and closed report/comparer;
- A-reference worktree reverting exactly two accepted behaviors;
- private A1/B/A2 reports and sanitized English result;
- default-off manual Web panel, prepare/report CLI and runbook steps;
- source/run/review evidence and current documentation synchronization.

Exclusions:

- automatic Chrome control;
- microphone/fixed-WAV input in the deterministic lane;
- real Agent/Tool/Provider/network calls in deterministic A1/B/A2;
- mixing manual results with controlled populations;
- implementing any new optimization;
- Production telemetry, public retention/SLO or multi-user observability;
- physical first-audible or product-readiness claims.
