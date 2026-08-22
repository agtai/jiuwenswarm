# Live Voice latency optimization inventory

> Date: 2026-08-21
> Last synchronized: 2026-08-22
>
> This is a dated optimization/evidence snapshot, not the authority for current
> project status or execution priority. `live-voice/STATUS.md` remains the
> mutable authority, and Git remains the implementation fact. Headroom ranges
> below are not additive: several waits overlap, and perceived-response gains
> do not necessarily reduce final completion time.

## 1. Source-state boundary

The committed baseline inspected for `0812_live_voice_w3_renan` was
`2c543aef`; unrelated uncommitted working-tree changes were excluded. That
source predates the causally accepted optimization candidates. The P2 candidate
and accepted TTS component change live in separate latency branches and are
composed in optimized checkpoint source
`52f7bc54353fc2c212aab1246941674feb821a9e`. Its exact
sequential A reference is `1b0802cae9a6718c0d3326c1292f7475fdefe08c`. The
checkpoint evidence documentation referenced here was recorded at
`def1dc06bf93eaf9a35a2d6af0e8a7fcd9273c36`.

The later EOT/STT materiality screen is bound separately to clean source
`8e5dab8b8c6651b2be784cf103df9239a93814a0`; its reviewed documentation closure
is `4222d522f92951bfbdf2c1a694c696cf782f51a0`, with raw-retention status later
recorded at `4ddb8908ced58ea1448de60675f979ce21fdae8f`. Its deterministic
no-Chrome numbers must not be pooled with the real-Provider VAD/TTS experiments
or the combined checkpoint.

The stable-sentence Agent-to-TTS screen is bound separately to tested
JiuwenSwarm source `81903777f8dccb40ba2cb70fbe9b28d28d86c7f5` and Agent-Core
`94e10cb6102c36fe78a64547957c0def97299273`. It did not modify Runtime, P2,
Browser or the composed checkpoint and receives no product-behaviour credit.
Its durable-artifact binding was recorded at
`85fbcc516571350fc50974ef35bfb2f40e1c48c8`.

Status terms used here:

- **Accepted — causal component scope:** the named owner and boundary passed
  source-bound A1/B/A2 evidence, but has no physical Browser or product E2E
  credit.
- **Rejected:** the experiment produced evidence against the candidate; the
  product change was not retained.
- **Screened out / materiality `STOP`:** the measurement path was valid, but
  the observed headroom did not justify constructing the product candidate.
- **Planned/conditional:** no product credit exists; implementation proceeds
  only after the stated measurement gate.
- **Estimated:** planning headroom inferred from current code facts or
  historical evidence, not a measured current-source improvement.

## 2. Validation ladder and completion credit

The agreed optimization loop is layered. A cheap screen may reject a weak
hypothesis before product wiring, but a passing component experiment is only a
candidate and cannot by itself close the optimization:

| Gate | Required path | Credit granted |
|---|---|---|
| **A — deterministic causal** | Same source, controlled inputs, one changed variable, A/B/A where applicable, exact stage and forbidden-effect accounting | Component mechanism and causal headroom only |
| **B — real Agent/Provider** | Current real Agent and/or Speech Provider for the boundary being changed, with exact model/config/source labels | Real dependency timing and semantic integrity for that component |
| **C — deployed Live Voice A/B** | JiuwenSwarm deployed, Live Voice enabled, optimization off/on under the same environment/config/input; every workload completes and the affected output/TTS/Task truth succeeds | Product-path acceptance for the declared environment; physical first-audible/device credit only when Browser/audio is actually exercised |

Gate C uses the same three workload classes agreed with Hongxing:

| Workload | Prompt |
|---|---|
| Short | “What is the capital of France? Answer with the city name only.” |
| Medium | “Explain the complete water cycle in nature in 5 points.” |
| Long | “Please introduce Hangzhou in 8 detailed points, with at least two sentences for each point, then give a summary.” |

For each prompt, record task/response success, TTS/playout success where
applicable, stage-by-stage latency and total latency. A faster failed workflow
is a regression, not an accepted optimization. Direct audio/prompt injection is
valid for Gates A/B; it does not replace the deployed Live Voice Gate C.

The bounded P2 pull currently demonstrates this distinction. Its repository
A/B/A evidence passed Gate A, and Hongxing externally reported approximately
46% faster response completion in a deployed validation. That same run failed
TTS with `SPEECH_OPERATION_NOT_AUTHORIZED`; retry did not recover and the page
required refresh. The external percentage has no source-bound artifact in this
repository yet and is therefore **REPORTED**, not locally credited.

The optimized checkpoint/EOT source supports the reported cause: the Web owner
validates an entire `notification_batch` before queueing its items, but
`DedicatedMediaProductRegistry.observe_agent_response()` observes only a
top-level `notification` and ignores the final notification nested in the
batch. The required repair must validate the complete batch before effects,
then process every item in order so the final item can establish TTS authority;
an invalid batch must grant zero partial authority.

## 3. Completed experiments

| Optimization | Status | Area / code ownership | Observed headroom or result | Current evidence | Comment |
|---|---|---|---:|---|---|
| P2 bounded notification pull, batch size 16 | **CAUSAL CANDIDATE ACCEPTED; DEPLOYED VALIDATION FAILED — FIX/RETEST REQUIRED** | P2; `productWebActivation.ts`, `LiveVoiceIntegratedRoutePanel.tsx`, `product_composition_registry.py`, `product_p2_interaction_adapter.py`, `agent_conversation_runtime.py`, media response observer | Repository p50 saved approximately **0.78 s / 4.00 s / 8.04 s** for 10/50/100 notifications; deployed improvement **~46% REPORTED** by Hongxing | A1/B/A2: 864→86 ms, 4348→344 ms, 8658→615 ms; 15/15 successful in every repository population; deployed response completed faster but TTS failed with `SPEECH_OPERATION_NOT_AUTHORIZED` | Component causality remains valid, but product acceptance is blocked until atomic batch observation is fixed and the short/medium/long deployed A/B passes without refresh or TTS failure. |
| TTS downlink decoupled from successor-capture ACK | **ACCEPTED — first-audio causal component scope** | P1/P2 seam; `productP1VoiceRoute.ts`, `dedicated_media_registration.py` | First-source p50 saved **5.8 ms / 255.1 ms / 756.1 ms** under injected ACK delays of 0/250/750 ms | A1/B/A2 returned to the original timing; at 750 ms, first source changed from 756.5 to 0.48 ms | It improves first audio, but confirmed receipt remains ACK-delayed. Real E2E gain depends on the checkpoint and later physical validation. |
| Fixed VAD reduction from 1200 to 900/800 ms | **REJECTED** | P1 input; `streaming_speech.py`, `openai_streaming_speech.py` | Successful turns exposed **285–412 ms** of potential endpointing headroom | Both candidates preserved only 15/20 turns; every 1000 ms natural-pause case failed 0/5 | The headroom is real, but a global fixed threshold cannot safely recover it. Keep 1200 ms. |
| Application-level TTS HTTPX client reuse | **REJECTED AND REVERTED** | P1 TTS Provider; `openai_streaming_speech.py` | No gain; warm first-PCM regressed **57.8 ms / 7.0%** | B produced **0/3 warm TCP/TLS reuse**; 832.0→889.9 ms warm p50 | Do not reintroduce this implementation unchanged. |
| Runtime-owned stable-sentence Agent→TTS overlap | **SCREENED OUT — MATERIALITY `STOP` FOR TESTED WORKLOADS** | Pure response policy, real formal Agent and benchmark-only real TTS; no Runtime/P2/Browser wiring | Candidate→final/projected-gain p50 **177.2 ms**, p95 **425.3 ms**; relative p50 **7.43%** | 3/3 real pilot attempts completed, exact prefix 3/3, mismatch 0, zero forbidden effects; credited v2 artifacts survive in the durable latency-runs archive with matching hashes | Failed the predeclared 500 ms headroom, 400 ms gain and 10% relative gates. Reopen only with a reviewed new long-form workload/materiality hypothesis; do not generalize this STOP to every possible response length. |
| Accepted-optimizations combined checkpoint | **IMPROVED — DETERMINISTIC NO-CHROME CHECKPOINT COMPLETE AND REVIEWED** | Deterministic P1/P2 composition; `acceptedOptimizationsCheckpoint.ts` plus real P1/P2 owners | W1 **1015 ms / 12.688%**; W2 **4660 ms / 31.275%**; W3 **8570 ms / 49.971%** | A1, B and A2 each completed 15/15 attempts; A1/A2 drift was exactly 0% | This proves controlled owner-path gain only. It does not exercise the raw P2 response observer that caused the deployed TTS authorization failure, nor real Provider/network/Chrome/WebAudio/Agent/model timing. |
| EOT/STT early result waiter | **REJECTED — NO MATERIAL SERIAL GAP** | P1/P2 Speech settlement; real `ProductP1VoiceRouteOwner` and registry result seam under deterministic dependencies | Largest removable-gap p50 **0.885 ms**; largest fraction p50 **0.015** | Complete A1 at `8e5dab8b8`: 20/20 exact, cleanup-complete attempts; ten marks/eight segments; zero forbidden effects | The 450.782 ms provider-slow diagnostic is legitimate remaining Provider wait. The credited final raw `/tmp` report no longer exists; reviewed sanitized tables remain authoritative, while an earlier diagnostic 20/20 raw report survives. Future credited runs must use the durable latency-runs root. |

## 4. Combined checkpoint result

The deterministic checkpoint measures from `speech_end` to
`confirmed_ack_and_next_turn_ready` on one injected monotonic scheduler. It
executes the real P1/P2 owners while keeping Provider, network, Agent/model and
playout durations controlled. Therefore these totals are controlled owner-path
measurements, not physical end-to-end latency.

| Workload | A1 p50 | B p50 | A2 p50 | Absolute gain | Relative gain |
|---|---:|---:|---:|---:|---:|
| W1 — short dialogue | 8000 ms | 6985 ms | 8000 ms | 1015 ms | 12.688% |
| W2 — long dialogue | 14900 ms | 10240 ms | 14900 ms | 4660 ms | 31.275% |
| W3 — Tool-style | 17150 ms | 8580 ms | 17150 ms | 8570 ms | 49.971% |

All three populations completed 15/15 attempts, and A1/A2 drift was 0%. The
measured reduction decomposes exactly as follows:

| Workload | P2 bounded pull | TTS–successor ACK overlap | Total gain |
|---|---:|---:|---:|
| W1 | 765 ms | 250 ms | 1015 ms |
| W2 | 3910 ms | 750 ms | 4660 ms |
| W3 | 7820 ms | 750 ms | 8570 ms |

The optimized B residual is dominated by controlled playout duration and the
controlled Agent/model interval, not by the accepted P2/TTS waits. P2 final
delivery is now 85/340/680 ms for W1/W2/W3, while the accepted TTS overlap
reduces `tts_ready_to_downlink` from 250/750/750 ms to 0 ms in this scheduler.

## 5. Stage-by-stage evidence for completed experiments

The tables below deliberately remain separate. The checkpoint and standalone
P2/TTS owner experiments use deterministic monotonic schedulers, while the VAD
and connection experiments call the real Provider. A duration from one table
must not be added to a duration from another as though they shared one physical
clock or environment.

### 5.1 Accepted combined checkpoint

These are deterministic p50 values. A1 and A2 are identical for every row, and
p95 equals p50 because every fixture delay is controlled. `A` below therefore
means both A1 and A2.

| Stage | W1 A→B | W1 gain | W2 A→B | W2 gain | W3 A→B | W3 gain | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| STT settlement | 400→400 ms | 0 ms | 400→400 ms | 0 ms | 400→400 ms | 0 ms | Controlled external wait; unchanged |
| Admission | 500→500 ms | 0 ms | 500→500 ms | 0 ms | 500→500 ms | 0 ms | Controlled external wait; unchanged |
| Agent/model | 2000→2000 ms | 0 ms | 2000→2000 ms | 0 ms | 2000→2000 ms | 0 ms | Controlled external wait; unchanged |
| P2 final delivery | 850→85 ms | **765 ms** | 4250→340 ms | **3910 ms** | 8500→680 ms | **7820 ms** | Bounded pull removes most serialized notification RPC cycles |
| TTS generation | 1000→1000 ms | 0 ms | 1000→1000 ms | 0 ms | 1000→1000 ms | 0 ms | Controlled external wait; unchanged |
| TTS ready→downlink | 250→0 ms | **250 ms** | 750→0 ms | **750 ms** | 750→0 ms | **750 ms** | Successor-capture readiness no longer blocks downlink opening |
| Downlink→first source | 0→0 ms | 0 ms | 0→0 ms | 0 ms | 0→0 ms | 0 ms | No injected residual in this checkpoint |
| First source→playout | 3000→3000 ms | 0 ms | 6000→6000 ms | 0 ms | 4000→4000 ms | 0 ms | Controlled PCM duration; unchanged |
| Playout→confirmed ACK | 0→0 ms | 0 ms | 0→0 ms | 0 ms | 0→0 ms | 0 ms | No injected residual in this checkpoint |
| **Round total** | **8000→6985 ms** | **1015 ms** | **14900→10240 ms** | **4660 ms** | **17150→8580 ms** | **8570 ms** | Exact sum of the P2 and TTS gains above |

This table proves where the checkpoint gain comes from: **100% of the measured
reduction is explained by P2 final delivery plus TTS-ready-to-downlink overlap**.
STT, admission, Agent/model, TTS generation and controlled playout did not
change.

### 5.2 Causally accepted P2 bounded-pull experiment — deployed failure open

This standalone causal experiment measures the real P2 owner from an available
notification backlog to consumption of the authoritative final notification.
RPC counts are totals across five attempts; timings are p50.

| Notifications | A1 RPC / p50 | B RPC / p50 | A2 RPC / p50 | B gain vs A1 | What changed |
|---:|---:|---:|---:|---:|---|
| 10 | 50 / 864.293 ms | 5 / 85.823 ms | 50 / 860.659 ms | **778.470 ms** | One batch RPC per attempt instead of ten single-item RPCs |
| 50 | 250 / 4348.227 ms | 20 / 343.704 ms | 250 / 4305.376 ms | **4004.523 ms** | Four bounded batch RPCs per attempt instead of fifty single-item RPCs |
| 100 | 500 / 8658.478 ms | 35 / 615.209 ms | 500 / 8643.205 ms | **8043.269 ms** | Seven bounded batch RPCs per attempt instead of one hundred single-item RPCs |

No Agent/model, STT, TTS, WebAudio or physical network stage was measured by
this experiment. The gain comes specifically from reducing the number of
serialized P2 request/response cycles while preserving ordered barriers.

It did not cover the Gateway Media response observer. In the deployed run
reported by Hongxing, faster completion was followed by
`SPEECH_OPERATION_NOT_AUTHORIZED`, retry could not recover, and page refresh
was required. Current code explains the gap: the frontend parser validates the
whole batch and queues its tail, but the Gateway observer authorizes synthesis
only from a top-level single `notification`. Until the observer validates a
whole batch atomically and processes every valid item in order, the P2 change
is a causal candidate with a failed product gate, not a complete optimization.

### 5.3 Accepted TTS successor-ACK decoupling experiment

These p50 values start at `TTS descriptor ready`. The candidate does not make
successor capture ACK arrive earlier. It allows downlink and first-source work
to proceed while that ACK remains pending.

#### Injected successor ACK delay: 250 ms

| Boundary | A1 | B | A2 | B−A1 | Interpretation |
|---|---:|---:|---:|---:|---|
| TTS descriptor ready | 0.001 ms | 0.001 ms | 0.001 ms | 0.000 ms | Unchanged origin |
| Successor capture requested | 0.039 ms | 0.031 ms | 0.037 ms | -0.008 ms | Noise-scale difference |
| Successor first ACK | 251.138 ms | 252.292 ms | 251.031 ms | **+1.154 ms** | ACK itself did not improve |
| Downlink opened | 255.215 ms | 0.107 ms | 254.573 ms | **-255.108 ms** | Main removed serialization point |
| Downlink first frame | 255.511 ms | 0.404 ms | 254.882 ms | **-255.107 ms** | First frame follows the earlier downlink |
| First source scheduled | 255.597 ms | 0.486 ms | 254.980 ms | **-255.111 ms** | Accepted first-audio component gain |
| Playout receipt accepted | 266.612 ms | 254.023 ms | 265.533 ms | **-12.589 ms** | Receipt remains mostly ACK-delayed |

#### Injected successor ACK delay: 750 ms

| Boundary | A1 | B | A2 | B−A1 | Interpretation |
|---|---:|---:|---:|---:|---|
| TTS descriptor ready | 0.001 ms | 0.001 ms | 0.001 ms | 0.000 ms | Unchanged origin |
| Successor capture requested | 0.024 ms | 0.037 ms | 0.025 ms | +0.013 ms | Noise-scale difference |
| Successor first ACK | 751.212 ms | 751.498 ms | 751.201 ms | **+0.286 ms** | ACK itself did not improve |
| Downlink opened | 756.054 ms | 0.125 ms | 753.980 ms | **-755.929 ms** | Main removed serialization point |
| Downlink first frame | 756.458 ms | 0.413 ms | 754.668 ms | **-756.045 ms** | First frame follows the earlier downlink |
| First source scheduled | 756.542 ms | 0.476 ms | 754.721 ms | **-756.066 ms** | Accepted first-audio component gain |
| Playout receipt accepted | 767.439 ms | 753.939 ms | 766.050 ms | **-13.500 ms** | Receipt remains mostly ACK-delayed |

At 1100 ms, A1/A2 failed before downlink, whereas B rendered once and then
reported truthful degraded interruption. That is a reliability/ordering
improvement, not a directly comparable successful-turn latency delta.

### 5.4 Rejected fixed-threshold VAD experiment

This experiment uses the real OpenAI streaming recognition Provider. Values are
aggregate successful-attempt p50; outcome integrity remains part of the result.

| Stage / outcome | A1 1200 ms | E1 900 ms | E1−A1 | E2 800 ms | E2−A1 | A2 1200 ms | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| Successful turns | 20/20 | **15/20** | -5 turns | **15/20** | -5 turns | 20/20 | Both lower thresholds split every 1000 ms pause case |
| Final voiced frame→EOT | 1508.675 ms | 1216.858 ms | **-291.817 ms** | 1096.765 ms | **-411.910 ms** | 1503.845 ms | Endpointing became faster on surviving turns |
| EOT→STT final | 388.360 ms | 410.643 ms | **+22.283 ms** | 389.902 ms | **+1.542 ms** | STT finalization did not improve |
| Final voiced frame→STT final | 1907.360 ms | 1631.459 ms | **-275.901 ms** | 1503.506 ms | **-403.854 ms** | 1917.071 ms | Total successful-turn gain comes almost entirely from earlier EOT |

The candidate was rejected because the latency gain was purchased by false
endpointing. The valid headroom is therefore the 285–412 ms endpointing region,
but it must be recovered through semantic/adaptive logic with a safe 1200 ms
fallback rather than another global fixed threshold.

### 5.5 Rejected TTS Provider connection-reuse experiment

This experiment calls the real `OpenAIStreamingSpeechProvider` directly. It
contains no Gateway, Browser, WebAudio or playout receipt. Positive deltas are
regressions.

| Position | Boundary | A1-v2 p50 | B p50 | B−A1 | Interpretation |
|---|---|---:|---:|---:|---|
| Cold | Response headers | 1023.1 ms | 1110.1 ms | **+86.9 ms** | Slower |
| Cold | First Provider audio | 1025.0 ms | 1111.4 ms | **+86.4 ms** | Slower |
| Cold | First PCM | 1039.6 ms | 1116.8 ms | **+77.2 ms** | Slower |
| Cold | Completed | 1808.3 ms | 1812.8 ms | **+4.5 ms** | Essentially neutral/slightly slower |
| Warm | Response headers | 825.4 ms | 883.6 ms | **+58.1 ms** | Slower |
| Warm | First Provider audio | 826.7 ms | 884.8 ms | **+58.0 ms** | Slower |
| Warm | First PCM | 832.0 ms | 889.9 ms | **+57.8 ms / 7.0%** | Acceptance metric regressed |
| Warm | Completed | 1718.1 ms | 1732.6 ms | **+14.5 ms** | Slower |

All B attempts, including all three warm attempts, opened fresh TCP/TLS
connections. The proposed application-client retention therefore removed no
connection-establishment stage and was reverted. A bounded post-`audio.done`
EOF drain is only a separate hypothesis; it receives no headroom credit from
this failed candidate.

### 5.6 Rejected EOT/STT early-wait experiment

This deterministic no-Chrome A1 measures the real Product P1 owner and real
registry result seam with controlled local-settlement and Provider-final
readiness. A product candidate required both removable-gap p50 at least 80 ms
and removable-gap-fraction p50 at least 0.10. All 20 attempts were exact and
cleanup-complete, with one result RPC each and zero forbidden effects.

The eligible tail begins only after both independent facts are ready:

```text
removable serial gap = result returned - max(route settled, Provider final ready)
```

| Fixture | EOT→capture | stopped→ACK | ACK→settled | EOT→Provider | settled→request | request→return | diagnostic settled→return | EOT→final | removable | fraction |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| local-fast/provider-fast | 0.194 ms | 0.091 ms | 52.219 ms | 51.594 ms | 0.008 ms | 0.770 ms | 0.779 ms | 53.479 ms | **0.779 ms** | **0.015** |
| local-slow/provider-fast | 0.120 ms | 0.025 ms | 502.165 ms | 51.490 ms | 0.011 ms | 0.869 ms | 0.880 ms | 503.173 ms | **0.880 ms** | **0.002** |
| local-fast/provider-slow | 0.077 ms | 0.012 ms | 51.872 ms | 501.883 ms | 0.007 ms | 450.775 ms | 450.782 ms | 502.774 ms | **0.885 ms** | **0.002** |
| both-slow | 0.089 ms | 0.012 ms | 502.442 ms | 501.635 ms | 0.006 ms | 0.796 ms | 0.802 ms | 503.564 ms | **0.802 ms** | **0.002** |

Values are p50; complete p50/nearest-rank-p95 tables remain branch-bound at
`latency/eot-stt-settlement-overlap:live-voice/evidence/EOT_STT_SETTLEMENT_MATERIALITY_RESULT_2026-08-21.md`.
The provider-slow fixture demonstrates why the diagnostic route wait is not
headroom: almost all 450.782 ms elapsed before Provider final readiness, leaving
only 0.885 ms after both join inputs were ready. The closed decision is
`NO_MATERIAL_SERIAL_GAP`; no product/wire change was implemented.

The credited final raw report was written under volatile `/tmp` and is no
longer present. The reviewed sanitized tables remain the credited record. An
earlier diagnostic A1 raw report survives under the durable
`/home/renan/openJiuwen-ai/live-voice-latency-runs/` root but is not the final
population. This weakens re-reduction availability, not the reviewed STOP
decision; future credited runs must retain raw artifacts durably.

### 5.7 Screened stable-sentence Agent→TTS overlap

This no-Chrome screen asks whether an exact-prefix complete sentence appears
early enough in the real formal Agent stream to justify benchmark-only TTS
before `chat.final`. It does not claim that Runtime, P2 or Browser can already
present such speech safely. Starting the same TTS request earlier can hide only
the candidate-to-final interval; it does not make Agent or TTS generation
faster.

Agent boundaries and candidate→final are **MEASURED** on one monotonic process.
TTS request→first PCM is **MEASURED** on the real streaming Provider.
Candidate-path first PCM and projected gain are **DERIVED**. The final-gated
baseline is **ESTIMATED** using the same observed TTS duration; Browser
first-audible and playout are **UNKNOWN**.

| Public case | Candidate | Final | Candidate→final | TTS request→first PCM | Candidate-path first PCM | Estimated final-gated first PCM | Projected gain |
|---|---:|---:|---:|---:|---:|---:|---:|
| Two-sentence explanation | 1896.5 ms | 2073.7 ms | **177.2 ms** | 1777.4 ms | 3673.9 ms | 3851.1 ms | **177.2 ms** |
| Three-sentence comparison | 683.3 ms | 1108.5 ms | **425.3 ms** | 1125.5 ms | 1808.8 ms | 2234.0 ms | **425.3 ms** |
| Short technical summary | 698.7 ms | 826.8 ms | **128.1 ms** | 896.6 ms | 1595.3 ms | 1723.4 ms | **128.1 ms** |
| **p50** | **698.7 ms** | **1108.5 ms** | **177.2 ms** | **1125.5 ms** | **1808.8 ms** | **2234.0 ms** | **177.2 ms** |
| **p95 nearest-rank** | **1896.5 ms** | **2073.7 ms** | **425.3 ms** | **1777.4 ms** | **3673.9 ms** | **3851.1 ms** | **425.3 ms** |

| Materiality gate | Required | Observed | Result |
|---|---:|---:|---|
| Candidate→final p50 | at least 500 ms | 177.2 ms | fail |
| Projected first-PCM gain p50 | at least 400 ms | 177.2 ms | fail |
| Projected relative gain p50 | at least 10% | 7.43% | fail |
| Useful trace classes | at least 2 | 3 | pass |
| Prefix mismatches / forbidden effects | 0 / 0 | 0 / 0 | pass |

The earlier 1.5–2.5 second ordinary estimate is not credited. The screen
stopped before authority, correction, cancellation, P2 and Browser work.
Reopening requires a new representative workload/materiality hypothesis and
the same exact-prefix gate. Complete evidence remains branch-bound at
`latency/stable-sentence-agent-tts:live-voice/evidence/STABLE_SENTENCE_AGENT_TTS_CAUSAL_RESULT_2026-08-21.md`.
The credited v2 raw artifacts survive at
`/home/renan/openJiuwen-ai/live-voice-latency-runs/stable-sentence-screen-20260821/`;
their recorded hashes were rechecked on 2026-08-22. Superseded unversioned
pilot directories retain no credit.

## 6. Recommended next optimization candidates

The reference numbers below are stable inventory labels, not execution
priority. The execution order later in this document additionally accounts for
dependencies, risk, evidence gates and whether Chrome is required.

| Ref | Candidate | Status | Expected headroom | Area / likely code | Current evidence and rationale |
|---:|---|---|---:|---|---|
| 1 | EOT/STT early result waiter with authoritative join | **REJECTED — NO MATERIAL SERIAL GAP** | No qualifying removable tail | `productP1VoiceRoute.ts`, `gatewayBatchSpeechClient.ts`, `dedicated_media_registration.py` | Complete A1 at `8e5dab8b8` retained ten marks/eight segments in 20/20 exact cleanup-complete attempts with zero forbidden effects. The largest respective removable-gap/fraction p50 values were 0.885 ms and 0.015; the 450.782 ms route-to-return diagnostic is legitimate Provider wait and does not authorize B. |
| 2 | Provider-native Semantic VAD with 1200 ms fallback | **SPECIFIED — NEXT CAUSAL SCREEN** | **250–400 ms hypothesis**, not accepted gain | P1 Interaction Intelligence; `streaming_speech.py`, `openai_streaming_speech.py`, no-Browser validation runner | Fixed 800/900 ms exposed 285–412 ms only on successful cases and failed natural-pause integrity. The approved Tier-3 screen compares separate `auto` and `high` A/B/A blocks without another RPC; product activation and Gate C remain excluded. The spec remains branch-bound at `latency_checkpoint_accepted_optimizations:live-voice/roadmap/SEMANTIC_VAD_CAUSAL_BENCHMARK_SPEC_2026-08-21.md`. |
| 3 | Hybrid local + Provider VAD arbitration | **PROPOSED, HIGHER COMPLEXITY** | **300–500 ms** | Browser capture/VAD plus Gateway speech owner | Potentially larger endpointing gain, but requires one exact commit authority and conflict arbitration between endpoint detectors. |
| 4 | Adaptive WebAudio startup lead | **PROPOSED — PHYSICAL WATERFALL/SPEC FIRST** | **700–840 ms estimated** | `browserAudioIOAdapter.ts`; current fixed `PLAYOUT_STARTUP_LEAD_SECONDS = 1.0` | Strongest remaining code-fact estimate, not measured physical headroom. A bounded 160–300 ms decoded reserve can be screened cheaply, but Chrome/device evidence is required for underrun and first-audible acceptance. |
| 5 | Separate receipt settlement from successor readiness | **OPEN AUTHORITY QUESTION** | Controlled wait exposed at approximately **254/754/1007 ms** for 250/750/1100 ms injected delays | `productP1VoiceRoute.ts`, P2 presentation ACK and next-turn ownership | First audio is already decoupled, but terminal receipt still follows successor readiness. Any optimization must retain truthful playout and interruption authority. |
| 6 | Runtime-owned stable-sentence Agent→TTS overlap | **SCREENED OUT — MATERIALITY `STOP` FOR TESTED WORKLOADS** | Real three-case pilot: **177.2 ms p50 / 425.3 ms p95**, relative p50 **7.43%** | Pure policy and no-Chrome runner only; no Runtime/P2/Browser product wiring | Three of three real formal-Agent/real-TTS attempts completed with exact prefixes and zero forbidden effects, but failed the 500 ms headroom, 400 ms gain and 10% gates. The earlier 1.5–2.5 s ordinary estimate is not credited; any long-form retry requires a new reviewed hypothesis. |
| 7 | Bounded next-sentence TTS prefetch | **PROPOSED** | **100–800 ms between sentences** | Conversation Runtime, streaming synthesis route, bounded semantic queue | Primarily improves continuity, not first-sentence latency. It must discard prefetched speech on replacement/barge-in. |
| 8 | Fixed authoritative phrase cache | **PROPOSED** | **800–1400 ms per cache hit** | Conversation Runtime and TTS cache keyed by text hash, locale, model, voice and render version | Suitable only for stable non-private acknowledgements. It must not cache arbitrary Agent or user content. |
| 9 | Authoritative accepted/queued acknowledgement | **PROPOSED P3 PERCEIVED-LATENCY OPTIMIZATION** | **2–7 s perceived** | Conversation Runtime, Task Core truth, PresentationUnit/TTS | It does not shorten final Task completion. It gives the user a truthful early response such as “accepted” or “queued.” |
| 10 | Short Task status/cancel PresentationUnits | **PROPOSED P3** | **1–5 s perceived** | `voice_task_bridge.py`, `product_composition_registry.py`, presentation/TTS | It must speak only authoritative Task state and never promote accepted/queued to running/completed. |
| 11 | Structured Task route avoiding unnecessary dialogue | **MEASURE FIRST** | **1–6 s where applicable** | `voice_task_bridge.py`, composition registry | This route partially exists already. Benchmark before expanding it; otherwise the estimate may double-count existing behavior. |

## 7. Residual P2 candidates

These candidates are frozen until the current batch-observer defect is fixed
and Gate C shows substantial residual backlog. The deterministic checkpoint
alone cannot justify more P2 transport work.

| Candidate | Status | Expected headroom | Code area | Comment |
|---|---|---:|---|---|
| Batch size 16→32 | **OPTIONAL** | **170–255 ms** at 50–100 pure-observer events | Web P2 owner and server notification registry | At 85 ms per RPC, 50 events fall from four pulls to two and 100 events from seven to four; authoritative barriers can reduce the realized gain. |
| Server push / single-writer delivery | **DEFERRED** | **200–500 ms** on high backlog | WebSocket/Gateway P2 protocol and replay owner | Larger protocol change involving reconnect, replay and backpressure. |
| Coalesce pure reasoning/delta observations | **PROPOSED WITH STRICT BARRIERS** | **100–400 ms** on high backlog | Agent event queue and P2 notification publisher | Never coalesce final, error, Tool, Task or Presentation barriers. |
| ACK/next-turn processing overlap | **LOWER PRIORITY** | **50–150 ms** | P1/P2 ACK and successor-capture lifecycle | Mostly improves next-turn readiness, not first audible response. |
| PresentationUnit handoff tuning | **NOT A PRIMARY TARGET** | **<50 ms** | Conversation Runtime → presentation seam | Existing observations are roughly 16–68 ms. |

## 8. Low-confidence or deferred ideas

| Candidate | Status | Headroom | Reason |
|---|---|---:|---|
| Bounded `audio.done → EOF` drain followed by connection reuse | **NEW SPEC REQUIRED** | Unknown | The rejected experiment suggests premature SSE close may prevent pooling, but this is only a hypothesis. Actual warm reuse must be proven before estimating a gain. |
| STT session/pre-open tuning | **LOW PRIORITY** | **0–100 ms** | The streaming session already operates during capture. |
| Local faster-whisper as primary STT | **NOT RECOMMENDED CURRENTLY** | Likely regression to at most 100 ms gain | It loses the existing streaming advantage and introduces CPU/quality risk. |
| Blanket 64-frame media queue | **REJECTED DESIGN DIRECTION** | No credible latency gain | It could add up to 1.28 s of stale/cancellation backlog. Use a bounded 12–16-frame window only if starvation evidence requires it. |
| Global 500 ms VAD | **REJECTED DESIGN DIRECTION** | Superficially about 700 ms | It contradicts the physical breath-pause repair and current 800/900 ms failure evidence. |
| Direct Browser TTS from raw Agent deltas | **REJECTED DESIGN DIRECTION** | Potentially large but unsafe | Provisional or rewritten text cannot be retracted after it is spoken. Authority belongs in Conversation Runtime. |
| Opus/codec replacement as the first lever | **DEFERRED** | Unproven | Existing 20 ms PCM framing is already appropriate for streaming; measured waits lie elsewhere. |

## 9. Recommended execution order

This order applies only after the latency workstream is activated. It does not
replace the current product-truth execution packet in `live-voice/STATUS.md`.

1. Repair the P2 Media observer: validate a complete `notification_batch`
   before effects, process valid items in order, let the final item establish
   TTS authority, and prove invalid batches grant zero partial authorization.
2. Run deployed Live Voice A/B with the fixed short/medium/long prompts,
   optimization off/on, identical environment/config, successful completion,
   TTS/playout truth and a stage/total waterfall. This closes or rejects the
   P2 product candidate; the externally reported 46% alone grants no credit.
3. In parallel, run the separately specified Provider-native Semantic VAD
   `auto` and `high` causal screens with the 1200 ms fallback. Treat this as
   Tier-3 Provider/commit/fence work, not a low-risk constant change.
4. Use the deployed waterfall to choose between an Adaptive WebAudio startup
   spec (first-audible) and receipt-settlement authority design
   (turn-completion/next-turn). Do not add their headroom estimates together.
5. Keep stable-sentence stopped for the tested workloads. Reopen only after
   Hongxing reviews a new long-form workload/materiality solution. Keep
   sentence prefetch independent and measure continuity before product code.
6. Consider authoritative P3 acknowledgements and fixed non-private phrase
   caching only when perceived Task latency is a product priority; neither
   shortens Task completion, and both retain Task/Presentation authority risk.
7. Revisit batch-32, push or coalescing only if the repaired Gate C waterfall
   demonstrates real P2 backlog.

## 10. Documentation evidence

The following paths and refs were inspected for this inventory. Some evidence
documents live only on their exact-source latency branches and therefore are
listed as branch-bound paths rather than current-tree links.

- `latency/p2-bounded-pull-b`:
  `live-voice/evidence/P2_NOTIFICATION_BOUNDED_PULL_CAUSAL_RESULT_2026-08-21.md`
- `latency/vad-eot-causal-benchmark`:
  `live-voice/evidence/VAD_EOT_CAUSAL_RESULT_2026-08-21.md`
- `latency/vad-eot-causal-benchmark`:
  `live-voice/evidence/LATENCY_CAUSAL_EXPERIMENTS_SUMMARY_2026-08-21.md`
- `latency/eot-stt-settlement-overlap`:
  `live-voice/evidence/TTS_FIRST_AUDIO_CAUSAL_RESULT_2026-08-21.md`
- `latency/tts-provider-connection-reuse`:
  `live-voice/roadmap/TTS_PROVIDER_CONNECTION_REUSE_RESULT_2026-08-21.md`
- `latency/stable-sentence-agent-tts`:
  `live-voice/evidence/STABLE_SENTENCE_AGENT_TTS_CAUSAL_RESULT_2026-08-21.md`
- `latency/eot-stt-settlement-overlap`:
  `live-voice/roadmap/NON_AGENT_P1_P2_P3_LATENCY_OPTIMIZATION_BRAINSTORM_2026-08-21.md`
- `latency/eot-stt-settlement-overlap`:
  `live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md`
- `latency/eot-stt-settlement-overlap`:
  `live-voice/roadmap/EOT_STT_SETTLEMENT_OVERLAP_SPEC_2026-08-21.md`
- `latency/eot-stt-settlement-overlap`:
  `live-voice/roadmap/EOT_STT_SETTLEMENT_OVERLAP_IMPLEMENTATION_PLAN_2026-08-21.md`
- `latency/eot-stt-settlement-overlap`:
  `live-voice/evidence/EOT_STT_SETTLEMENT_MATERIALITY_RESULT_2026-08-21.md`
- `latency_checkpoint_accepted_optimizations`:
  `live-voice/roadmap/SEMANTIC_VAD_CAUSAL_BENCHMARK_SPEC_2026-08-21.md`
- `latency_checkpoint_accepted_optimizations`:
  `live-voice/roadmap/SEMANTIC_VAD_CAUSAL_BENCHMARK_IMPLEMENTATION_PLAN_2026-08-21.md`
- `latency_checkpoint_accepted_optimizations`:
  `live-voice/roadmap/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_SPEC_2026-08-21.md`
- `latency_checkpoint_accepted_optimizations`:
  `live-voice/roadmap/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_IMPLEMENTATION_PLAN_2026-08-21.md`
- `latency_checkpoint_accepted_optimizations` at documentation HEAD
  `def1dc06bf93eaf9a35a2d6af0e8a7fcd9273c36`:
  `live-voice/evidence/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_2026-08-21.md`
- Hongxing source-bound physical findings:
  `WRAP_UP_HONGXING_LATENCY_FINDINGS_2026-08-21.md`
- Hongxing deployed bounded-P2 validation report, 2026-08-21: approximately
  46% faster response completion followed by
  `SPEECH_OPERATION_NOT_AUTHORIZED`, unrecoverable retry and required refresh.
  Branch, exact commit, reproduction logs and run artifacts remain pending, so
  this is external reported evidence rather than source-bound measurement.

## 11. Big-picture conclusion

The combined checkpoint now proves that the composed P2 candidate and accepted
TTS component change retain
controlled full-round gains of 1.015–8.570 seconds across W1–W3, with longer
notification-heavy workloads benefiting most, but deployed P2 validation also
found a TTS-authorization workflow defect; the P2 change remains a causal
candidate until repair and Gate C rerun. EOT/STT found at most 0.885 ms p50
removable tail and did not authorize a product change. Stable-sentence measured
only 177.2 ms p50 projected gain for the tested workloads and stopped before
product wiring. The next no-Chrome screen is Provider-native Semantic VAD,
while P2 repair and the deployed physical waterfall proceed as the product
validation lane. Adaptive WebAudio startup remains the largest code-fact
estimate, but its actual priority depends on that waterfall and physical
Browser evidence.
