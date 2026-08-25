# Live Voice latency optimization inventory — 2026-08-23/24 diagnostic addendum

> Date: 2026-08-21 — **DIAGNOSTIC UPDATE: 2026-08-24** (current source and
> screen credit corrected without changing the historical experiment tables)
> Last synchronized: 2026-08-25
>
> This is the detailed dated addendum containing the 2026-08-24 manual
> waterfall and playout diagnostic. The
> [canonical inventory](LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md) owns the
> synchronized candidate table and execution order; `live-voice/STATUS.md`
> remains the mutable product authority, and Git remains the implementation
> fact. Headroom ranges below are not additive: several waits overlap, and
> perceived-response gains do not necessarily reduce final completion time.
>
> The complete experiment/run ledger, method taxonomy, end-to-end boundaries
> and artifact-retention route are in
> [the latency experiment catalog](../evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md).
> This addendum does not override the canonical inventory or act as a second
> raw-run ledger.

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

On 2026-08-23 the latency lane first composed its P2 candidate with Hongxing's
lifecycle source, then recomposed onto accepted Hongxing source `c31e85ade`.
The latter owns the repaired atomic batch observation, D-094 default-on batch
size 16 and the successful audible-TTS human validation. Conflicted P2
product/test files were resolved in favour of `c31e85ade`; the earlier
latency-lane P2 product candidate is superseded. The unified-submit probe
instrumentation fix was subsequently propagated to `0812_live_voice_w3_renan`
(`6384b67b7`), `latency/p2-bounded-pull-b` (`6dae211af`) and
`latency_checkpoint_accepted_optimizations` (`6a5d5e723`). These integration
commits do not replace the checkpoint hashes above or add product credit.

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

LVL-10L is bound to integration branch `latency/hx-optimizations`. Its initial
real pilots used source `76f4413de`; the clean v2 pilot and stopped formal used
`bcbf6a423`, with installed Agent-Core `94e10cb6102c36fe78a64547957c0def97299273`.
Historical LVL-10 worker branches `latency/lvl10-provider-screen` and
`latency/lvl10-validation` remained predecessor history. LVL-10L changed only
validation runner, fixtures, tests and documentation; product source remained
on the one-request full-final route.

The Agent first-visible-delta baseline is separately bound to branch
`latency/agent-first-delta-probe`, JiuwenSwarm `f71a5d830` and installed
Agent-Core `94e10cb61`. It exercises a real formal Agent with tools disabled,
but bypasses Browser, Speech, presentation and playout.

LVL-13 is separately bound to branch
`latency/pre-final-stable-agent-tts-screen`, JiuwenSwarm
`9600adbcf214a6bbc9dd6e08db4a8c59697854d3` and installed Agent-Core
`94e10cb6102c36fe78a64547957c0def97299273`. It exercises real Agent and real
Speech Provider first PCM, but bypasses Runtime/P2, Browser, WebAudio and
physical playout.

Status terms used here:

- **Accepted — causal component scope:** the named owner and boundary passed
  source-bound A1/B/A2 evidence, but has no physical Browser or product E2E
  credit.
- **Rejected:** the experiment produced evidence against the candidate; the
  product change was not retained.
- **Screened out / materiality `STOP`:** the measurement path was valid, but
  the observed headroom did not justify constructing the product candidate.
- **Directional `STOP`:** a bounded pilot repeated material headroom, but the
  formal population was not completed and no product candidate is authorized.
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

The bounded P2 pull demonstrates this distinction. Its repository A/B/A
evidence passed Gate A, and Hongxing externally reported approximately 46%
faster response completion in an initial deployed validation. That run failed
TTS with `SPEECH_OPERATION_NOT_AUTHORIZED`; the percentage remains **REPORTED**,
not locally credited. Hongxing source `c31e85ade` subsequently repaired atomic
ordered batch observation and passed a scoped short/medium/long human run with
audible TTS. The follow-up supports D-094 default-on but did not reproduce a
compatible feature-off/on p50/p95 population.

## 3. Completed experiments

| Optimization | Status | Area / code ownership | Observed headroom or result | Current evidence | Comment |
|---|---|---|---:|---|---|
| P2 bounded notification pull, batch size 16 | **DONE — PRODUCT DEFAULT-ON AND HUMAN ACCEPTED (hx `c31e85ade`, D-094); supersedes the causal-only candidate** | P2; `productWebActivation.ts`, `LiveVoiceIntegratedRoutePanel.tsx`, `product_composition_registry.py`, `product_p2_interaction_adapter.py`, `agent_conversation_runtime.py`, media response observer | Repository p50 saved approximately **0.78 s / 4.00 s / 8.04 s** for 10/50/100 notifications; deployed improvement **~46% REPORTED** by Hongxing | A1/B/A2: 864→86 ms, 4348→344 ms, 8658→615 ms; 15/15 successful in every repository population; deployed response completed faster but TTS failed with `SPEECH_OPERATION_NOT_AUTHORIZED` | UPDATE 2026-08-23: Hongxing repaired the atomic batch observation (`dedicated_media_registration.py`), shipped batch-16 default-on and retired both deployment switches (D-094). Human acceptance passed with audible TTS (10.65/7.05/2.78–3.14 s); the formal off/on frozen-corpus waterfall was not run and stays unclaimed. |
| TTS downlink decoupled from successor-capture ACK | **ACCEPTED — first-audio causal component scope** | P1/P2 seam; `productP1VoiceRoute.ts`, `dedicated_media_registration.py` | First-source p50 saved **5.8 ms / 255.1 ms / 756.1 ms** under injected ACK delays of 0/250/750 ms | A1/B/A2 returned to the original timing; at 750 ms, first source changed from 756.5 to 0.48 ms | UPDATE 2026-08-23: retained receipt settlement was separately decoupled from successor generation by hx `1fec48027` (+ Tier-3 review in `c31e85ade`), closing inventory ref #5 without changing this experiment's first-audio credit. |
| Fixed VAD reduction from 1200 to 900/800 ms | **REJECTED** | P1 input; `streaming_speech.py`, `openai_streaming_speech.py` | Successful turns exposed **285–412 ms** of potential endpointing headroom | Both candidates preserved only 15/20 turns; every 1000 ms natural-pause case failed 0/5 | The headroom is real, but a global fixed threshold cannot safely recover it. Keep 1200 ms. |
| Application-level TTS HTTPX client reuse | **REJECTED AND REVERTED** | P1 TTS Provider; `openai_streaming_speech.py` | No gain; warm first-PCM regressed **57.8 ms / 7.0%** | B produced **0/3 warm TCP/TLS reuse**; 832.0→889.9 ms warm p50 | Do not reintroduce this implementation unchanged. |
| Historical LVL-07 stable-sentence Agent→TTS overlap | **ORIGINAL FIXTURES `STOP`; SUPERSEDED MATERIALITY QUESTION CONTINUES AS LVL-12/13** | Pure response policy, real formal Agent and benchmark-only real TTS; no Runtime/P2/Browser wiring | Historical projected gain p50 **177.2 ms**; later LVL-12 exact-prefix candidate→final p50 **1587.308 / 3573.381 ms** medium/long | Historical 3/3 result remains immutable; LVL-12 completes 10/10 and LVL-13 completes 30/30 on separate sources | Do not rewrite LVL-07. LVL-12/13 answer a new medium/long exact-prefix component hypothesis and still grant no product wiring. |
| LVL-10L completion-primary long-form chunked TTS | **DIRECTIONAL `STOP` — FORMAL ABORTED, NO PRODUCT CREDIT** | Validation-only post-final TTS runner; product source unchanged | Clean v2 pilot `long_2100`: B2 saved **6.93 s / 36.85%**, B4 saved **7.75 s / 41.27%** | 12/12 attempts, 24/24 requests, zero errors at `bcbf6a423`; prior v1 pilots isolated quota exhaustion and the one-request 8 MiB boundary | Repeats LVL-10's long direction but is one round. Hongxing requested stopping long-duration tests; no B2/B4 selection or Browser/product wiring. |
| Accepted-optimizations combined checkpoint | **IMPROVED — DETERMINISTIC NO-CHROME CHECKPOINT COMPLETE AND REVIEWED** | Deterministic P1/P2 composition; `acceptedOptimizationsCheckpoint.ts` plus real P1/P2 owners | W1 **1015 ms / 12.688%**; W2 **4660 ms / 31.275%**; W3 **8570 ms / 49.971%** | A1, B and A2 each completed 15/15 attempts; A1/A2 drift was exactly 0% | This proves controlled owner-path gain only. It does not exercise the raw P2 response observer that caused the deployed TTS authorization failure, nor real Provider/network/Chrome/WebAudio/Agent/model timing. |
| EOT/STT early result waiter | **REJECTED — NO MATERIAL SERIAL GAP** | P1/P2 Speech settlement; real `ProductP1VoiceRouteOwner` and registry result seam under deterministic dependencies | Largest removable-gap p50 **0.885 ms**; largest fraction p50 **0.015** | Complete A1 at `8e5dab8b8`: 20/20 exact, cleanup-complete attempts; ten marks/eight segments; zero forbidden effects | The 450.782 ms provider-slow diagnostic is legitimate remaining Provider wait. The credited final raw `/tmp` report no longer exists; reviewed sanitized tables remain authoritative, while an earlier diagnostic 20/20 raw report survives. Future credited runs must use the durable latency-runs root. |
| Agent start → first visible delta baseline | **MEASURED DIAGNOSTIC — NO PRODUCT CHANGE** | Formal real Agent seam; no Browser, STT, TTS, Tool or Task | First-delta p50 short/medium/long **522.856 / 543.185 / 591.914 ms**; delta→final p50 **8.779 / 1676.287 / 3518.228 ms** | 15/15 completed at `f71a5d830`; nearest-rank P95 first-delta **1337.260 / 682.479 / 742.521 ms**; zero forbidden effects | Medium/long timing windows justify an exact-prefix screen; the first delta itself has no stable-speech authority. See the [baseline](../evidence/AGENT_FIRST_DELTA_BASELINE_2026-08-25.md). |
| LVL-12 pre-final stable segmentation | **EXACT-PREFIX MATERIALITY PASS — NO PRODUCT/TTS AUTHORITY** | Validation-only real formal Agent policy/runner; no Browser, STT, TTS, Tool, Task or product wiring | Candidate→final p50 medium/long **1587.308 / 3573.381 ms**; Agent→candidate p50 **657.947 / 707.935 ms** | Accepted v2 10/10 at `ea6475120`, exact-prefix/terminal-complete throughout, zero forbidden effects | Its separate no-Browser Agent→TTS follow-up completed as LVL-13; LVL-12 itself grants no TTS/product credit. See the [LVL-12 result](../evidence/LVL12_PRE_FINAL_STABLE_SEGMENTATION_RESULT_2026-08-25.md). |
| LVL-13 pre-final exact-prefix Agent→TTS overlap | **ACCEPTED — REAL-AGENT/REAL-TTS COMPONENT; NO PRODUCT/BROWSER CREDIT** | Validation-only no-Browser A1/B/A2 runner; real formal Agent and Speech Provider | Agent→first-PCM p50 gain **1723.166 ms / 52.510% medium** and **3422.345 ms / 67.377% long** | Formal 30/30 at `9600adbcf`, exact-prefix completion, valid A1/A2 drift, zero forbidden effects; independent audit `C0/I0/M0` | Product-authority design and deployed physical Gate C remain required. See the [LVL-13 result](../evidence/LVL13_PRE_FINAL_STABLE_AGENT_TTS_RESULT_2026-08-25.md). |

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

### 5.2 Causally accepted P2 bounded-pull experiment and deployed follow-up

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

It did not cover the Gateway Media response observer. In the initial deployed
run
reported by Hongxing, faster completion was followed by
`SPEECH_OPERATION_NOT_AUTHORIZED`, retry could not recover, and page refresh
was required. The failing source explained the gap: the frontend parser
validated the whole batch and queued its tail, but the Gateway observer
authorized synthesis
only from a top-level single `notification`. Hongxing source `c31e85ade` later
repaired that observer, processed valid items in order and passed scoped human
validation with audible TTS. The original failed episode remains immutable;
the repair closes its functional defect without creating a frozen-corpus
off/on population or local credit for the reported 46%.

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

### 5.8 Post-integration physical waterfall — manual run `lv-manual-simple-to-paris-20260824-a`

First post-repair waterfall (commit `497831f58`, one completed round,
`dialogue_with_tool`, total EOT→ACK **7,310 ms**; diagnostic only):

| Segment | Today (measured) |
|---|---:|
| EOT→STT final | 702 ms |
| STT final→submit | 0.9 ms |
| submit→presentation (Agent+Tool) | 3,217 ms |
| presentation→TTS request | 0.3 ms |
| TTS request→downlink first frame | 1,561 ms |
| downlink→schedule | 0.8 ms |
| schedule→start estimate (fixed 1.0 s lead, zero underrun) | 579 ms |
| start estimate→playout complete | 1,218 ms |
| playout→ACK | 31 ms |

Other rounds of this run were cancelled/failed (reload before settlement;
the failed round hit the since-repaired `unified.submit` regression) and stay
in the denominator without timeline credit.

A later raw Browser batch in the same reused run directory recorded a completed
`dialogue_no_tool` round after the 250 ms screen hook was introduced:

| Screen observation | 1000 ms diagnostic round | 250 ms attributed round |
|---|---:|---:|
| Workload | `dialogue_with_tool` | `dialogue_no_tool` |
| schedule→start estimate | 578.998 ms ±41 ms | 46.703 ms ±42 ms |
| observed segment delta | — | **-532.295 ms / -91.9%** |

This is a promising physical signal, not a valid A/B population. The surviving
`run.json` still declares source `497831f58`, `product_code_dirty`, a 1000 ms
lead and no experiment identity; the two rounds use different workloads; the
250 ms batch was appended after the retained report was generated; and no
separate source/config-bound candidate report survives. The audible check was
clean, but candidate underrun/rebuffer counters are not bound in a regenerated
report. Production default therefore remains 1000 ms.

### 5.9 Current-source muted manual pilot — partial localization only

Two manual attempts on `37da36e68` used real Windows Chrome microphone input.
The first reproduced unintended barge-in; the second muted Windows output and
produced two completed dialogue batches plus four cancelled Task batches. No
true `task_cancel` batch was exported. Muted playout grants no physical
audibility credit, and the run is not a fixed-corpus baseline.

Cancelled batches retain useful observed mark pairs. The sanitized evidence
uses `0*` only as a display sentinel for a missing pair; canonical reports keep
those cells `unknown`, and zeros never enter statistics. Excluding missing
pairs, cross-profile diagnostic medians were:

| Boundary | Observed range | Diagnostic median | Credit |
|---|---:|---:|---|
| EOT -> STT final | 489.3–733.6 ms | **587.6 ms** | Partial localization only |
| TTS request -> first downlink | 1,360.4–1,572.3 ms | **1,518.3 ms** | Partial localization only |
| Schedule -> first-start estimate | 716.7–744.9 ms | **728.0 ms** | Partial localization only |
| Submit -> presentation | 1,229.2–122,981.3 ms | **1,753.0 ms** | Mixed workload/Agent/Task; not pure Live Voice |

For the two completed dialogues, TTS request→first Provider PCM was 1,216.9 /
1,151.8 ms; transport-open→first PCM was 13.1 / 12.3 ms; first PCM→first send
was 323.0 / 326.7 ms. These facts localize waits but do not re-authorize the
rejected connection-reuse candidate or prove a specific cause.

The attempt exposed a harness Gate: the current beep includes cancelled
batches, snapshots use the current stage rather than the batch profile and
wrapper shutdown can leave child processes. Another credited manual population
requires terminal/profile/round-aware advancement and complete process-tree
cleanup. See the
[sanitized pilot evidence](../evidence/MANUAL_MUTED_LATENCY_PILOT_20260824_37da36e68.md).

### 5.10 LVL-10L completion-primary long-form follow-up

LVL-10L separated completion from LVL-10's first-playable-reserve primary
metric and compared A1/B2/B4/A2 after one immutable authoritative final.

The first v1 pilot retained 12 attempts but opened only 18/24 requests because
OpenAI returned `429 credit_balance_exhausted`; it has zero timing credit. The
second v1 pilot opened 24/24 and completed 11/12, but its 2,938-character A2
control reached the 8 MiB wire-audio boundary. That corpus was retired without
raising the safety cap or crediting the candidate advantage.

The v2 corpus retained the same first 4/8/12 units (734/1,422/2,150 chars).
Its clean pilot completed 12/12, opened 24/24 requests and recorded zero errors:

| Workload completion | A1 | B2 | B4 | A2 |
|---|---:|---:|---:|---:|
| 600 | 8,516 ms | 4,498 ms | 5,715 ms | 6,759 ms |
| 1200 | 12,522 ms | 8,221 ms | 15,581 ms | 22,652 ms |
| 2100 | 18,852 ms | 11,878 ms | 11,029 ms | 18,755 ms |

At 2100 chars, time-interpolated paired completion gains were B2 **6,930 ms /
36.85%** and B4 **7,751 ms / 41.27%**. These are `DERIVED` from measured
component boundaries and one attempt per cell. They are not formal p50/p95.

The approved five-round/120-request formal was stopped on Hongxing's direction
before `attempts.jsonl` or a report was written; only run/manifest survive and
receive zero timing credit. See the
[LVL-10L result](../evidence/LVL10L_LONG_FORM_CHUNKED_TTS_RESULT_2026-08-24.md).

### 5.11 LVL-13 pre-final exact-prefix Agent→TTS component screen

LVL-12 first established that an exact-prefix candidate exists materially
before `chat.final` for medium/long workloads. LVL-13 then measured the next
boundary with the real formal Agent and real streaming Speech Provider. A1/A2
wait for final and synthesize the complete final; B sends the first
conservative candidate to TTS while Agent generation continues.

| Workload / arm | Agent→candidate p50 | Candidate→final p50 | Agent→final p50 | TTS request→first PCM p50 | Agent→first PCM p50 / p95 |
|---|---:|---:|---:|---:|---:|
| Medium A1 | 696.904 ms | 1531.904 ms | 2227.543 ms | 918.076 ms | 3140.796 / 3371.752 ms |
| Medium B | 634.413 ms | 1531.590 ms | 2166.120 ms | 868.886 ms | 1558.399 / 1875.545 ms |
| Medium A2 | 682.965 ms | 1523.338 ms | 2219.224 ms | 1022.340 ms | 3422.333 / 3857.015 ms |
| Long A1 | 700.731 ms | 3354.354 ms | 4055.085 ms | 982.608 ms | 4981.692 / 5351.788 ms |
| Long B | 692.352 ms | 3240.800 ms | 3938.775 ms | 970.890 ms | 1657.019 / 1707.368 ms |
| Long A2 | 693.380 ms | 3299.374 ms | 4050.683 ms | 1062.597 ms | 5177.037 / 5412.884 ms |

| Workload | Interpolated control p50 | B p50 | Gain | Relative gain | A1/A2 drift | Result |
|---|---:|---:|---:|---:|---:|---|
| Medium | 3281.565 ms | 1558.399 ms | **1723.166 ms** | **52.510%** | 281.537 ms / 8.964% | pass |
| Long | 5079.365 ms | 1657.019 ms | **3422.345 ms** | **67.377%** | 195.345 ms / 3.921% | pass |

| Stage | Medium control / B / delta | Long control / B / delta |
|---|---:|---:|
| Agent→candidate | 689.935 / 634.413 / **+55.522 ms** | 697.055 / 692.352 / **+4.703 ms** |
| Candidate→final | 1527.621 / 1531.590 / **−3.969 ms** | 3326.864 / 3240.800 / **+86.064 ms** |
| Agent→final | 2223.383 / 2166.120 / **+57.264 ms** | 4052.884 / 3938.775 / **+114.109 ms** |
| TTS dispatch→request | 0.118 / 0.065 / **+0.053 ms** | 0.217 / 0.038 / **+0.179 ms** |
| TTS request→first PCM | 970.208 / 868.886 / **+101.322 ms** | 1022.602 / 970.890 / **+51.712 ms** |
| **Agent→first PCM** | 3281.565 / 1558.399 / **+1723.166 ms** | 5079.365 / 1657.019 / **+3422.345 ms** |

Positive delta means B was faster. These overlapping p50 observations are not
additive; only Agent→first-PCM is the predeclared acceptance metric.

The formal population completed 30/30 after one excluded warm-up, with exact
prefixes and zero forbidden effects. The component candidate is accepted. Its
gain combines overlap with a shorter first TTS request; it does not isolate
those contributions or measure remaining-response completion. Runtime/P2,
Browser, WebAudio and physical first-audible remain outside credit. See the
[LVL-13 result](../evidence/LVL13_PRE_FINAL_STABLE_AGENT_TTS_RESULT_2026-08-25.md)
and [all-run appendix](../evidence/LVL13_PRE_FINAL_STABLE_AGENT_TTS_RUNS_2026-08-25.md).

## 6. Recommended next optimization candidates

The reference numbers below are stable inventory labels, not execution
priority. The execution order later in this document additionally accounts for
dependencies, risk, evidence gates and whether Chrome is required.

| Ref | Candidate | Status | Expected headroom | Area / likely code | Current evidence and rationale |
|---:|---|---|---:|---|---|
| 1 | EOT/STT early result waiter with authoritative join | **REJECTED — NO MATERIAL SERIAL GAP** | No qualifying removable tail | `productP1VoiceRoute.ts`, `gatewayBatchSpeechClient.ts`, `dedicated_media_registration.py` | Complete A1 at `8e5dab8b8` retained ten marks/eight segments in 20/20 exact cleanup-complete attempts with zero forbidden effects. The largest respective removable-gap/fraction p50 values were 0.885 ms and 0.015; the 450.782 ms route-to-return diagnostic is legitimate Provider wait and does not authorize B. |
| 2 | Provider-native Semantic VAD with 1200 ms fallback | **AUTO INTEGRITY REJECTED; PROTOCOL REPAIRED; HIGH NOT RUN** on `latency/semantic-vad-experiment` at `222582618` | Measured **684–734 ms EOT gain** on no-pause/300 ms only; zero credit for 600/1000 ms | P1 Interaction Intelligence; typed Speech/OpenAI/Gateway support and no-Browser runner | Protocol/fault repair passed 189 tests and two Tier-3 `C0/I0/M0` re-reviews. A full real A1/B/A2 pilot completed 12 slots: AUTO passed two cases but produced `EARLY_EOT` at 600/1000 ms. Preserve 1200 ms, reject AUTO and do not run HIGH. The canonical inventory owns the [controlled-audio construction and no-Browser method](LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md#lvl-08-controlled-audio-and-no-browser-method); see also the [retry result](../evidence/LVL08_SEMANTIC_VAD_AUTO_RETRY_RESULT_2026-08-25.md). |
| 3 | Hybrid local + Provider VAD arbitration | **PROPOSED, HIGHER COMPLEXITY** | **300–500 ms** | Browser capture/VAD plus Gateway speech owner | Potentially larger endpointing gain, but requires one exact commit authority and conflict arbitration between endpoint detectors. |
| 4 | Adaptive WebAudio startup lead | **TARGET MATERIALITY PASS; PHYSICAL ACCEPTANCE INCOMPLETE; DEFAULT REMAINS 1000 MS**. Hook remains clamped to [160,1000] ms; setup branch `latency/adaptive-playout-lead-experiment` at `5b37103a2` | **670.117–672.874 ms / 93.26–93.29% measured target headroom**; A1/A2 target drift **2.757 ms / 0.383%** | `browserAudioIOAdapter.ts`; private source-bound A1/B/A2 preparer/driver | Same-workload target values were 718.549/48.432/721.306 ms. A1/B completed; A2 cancelled after the target mark, so no physical completion/default credit follows. Upstream TTS/Agent drift consumed the target gain in total first-audio. See the [pilot result](../evidence/LVL09_ADAPTIVE_PLAYOUT_LEAD_PILOT_RESULT_2026-08-25.md). |
| 5 | Separate retained receipt settlement from successor readiness | **DONE — SCOPED LIFECYCLE SOURCE/AUTOMATION** — hx `1fec48027`, review in `c31e85ade` | Earlier controlled waits exposed approximately **254/754/1007 ms**; no new physical gain is credited | P2 activation journal, retained presentation ACK and next-turn ownership | The retained predecessor settles independently of the successor generation. This is lifecycle closure, not a p50/p95 latency population. |
| 6 | Pre-final stable-sentence Agent→TTS overlap | **LVL-13 COMPONENT CANDIDATE ACCEPTED; PRODUCT AUTHORITY/PHYSICAL GATE OPEN; SHORT `STOP`** | Agent→first-PCM p50 gain **1723.166 ms / 52.510% medium**, **3422.345 ms / 67.377% long** | LVL-12 exact-prefix 10/10 plus LVL-13 real-Agent/real-TTS 30/30 at `9600adbcf`; no Runtime/P2/Browser wiring | Define immutable presentation authority, reconciliation and cancellation before product wiring; then run deployed physical Gate C. |
| 7 | Bounded next-sentence TTS prefetch | **PROPOSED** | **100–800 ms between sentences** | Conversation Runtime, streaming synthesis route, bounded semantic queue | Primarily improves continuity, not first-sentence latency. It must discard prefetched speech on replacement/barge-in. |
| 8 | Fixed authoritative phrase cache | **PROPOSED** | **800–1400 ms per cache hit** | Conversation Runtime and TTS cache keyed by text hash, locale, model, voice and render version | Suitable only for stable non-private acknowledgements. It must not cache arbitrary Agent or user content. |
| 9 | Authoritative accepted/queued acknowledgement | **OPPORTUNITY SCREEN READY — CANDIDATE NOT IMPLEMENTED** on `latency/task-ack-latency-experiment` at `e38cb7b38` | **2–7 s perceived hypothesis**; actual gain `UNMEASURED` | Existing Task acceptance→presentation probe and offline strict reducer | Twelve tests prove strict canonical input, denominator/integrity precedence and private exclusive output. The screen measures only maximum opportunity; it neither accelerates Task completion nor proves spoken feedback. |
| 10 | Short Task status/cancel PresentationUnits | **PROPOSED P3** | **1–5 s perceived** | `voice_task_bridge.py`, `product_composition_registry.py`, presentation/TTS | It must speak only authoritative Task state and never promote accepted/queued to running/completed. |
| 11 | Structured Task route avoiding unnecessary dialogue | **MEASURE FIRST** | **1–6 s where applicable** | `voice_task_bridge.py`, composition registry | This route partially exists already. Benchmark before expanding it; otherwise the estimate may double-count existing behavior. |
| 12 | Authoritative-final chunked TTS | **INCONCLUSIVE — STOP BEFORE PRODUCT WIRING** | Primary reserve gain unresolved; long completion repeated **20–24%**, medium regressed **10–24%** | validation runner only; product route unchanged | Two formal real-Provider populations completed 45/45 with zero errors, but separate A1/A2 drift violations invalidated both causal decisions. No Browser Lane C or universal chunked route is authorized. Its separate completion-primary LVL-10L follow-up is also stopped. See the [result](../evidence/LVL10_AUTHORITATIVE_FINAL_CHUNKED_TTS_RESULT_2026-08-24.md). |
| 13 | LVL-10L completion-primary long-form chunked TTS | **DIRECTIONAL `STOP`; FORMAL NOT COMPLETED** | v2 pilot B2 **6.93 s / 36.85%**, B4 **7.75 s / 41.27%** saved at 2100 chars | validation runner/corpora only; product route unchanged | Clean 12/12 pilot repeats the long signal. Formal stopped before attempt artifacts. No further long-duration tests, arm selection or product wiring. |

## 7. Residual P2 candidates

The batch-observer defect was FIXED and default-on shipped (D-094), lifting
the freeze precondition. However, today's completed round showed no residual
notification-backlog pain (delivery segments ≈0–31 ms), so transport work
stays frozen until a future waterfall shows real backlog.

| Candidate | Status | Expected headroom | Code area | Comment |
|---|---|---:|---|---|
| Batch size 16→32 | **OPTIONAL** | **170–255 ms** at 50–100 pure-observer events | Web P2 owner and server notification registry | At 85 ms per RPC, 50 events fall from four pulls to two and 100 events from seven to four; authoritative barriers can reduce the realized gain. |
| Server push / single-writer delivery | **DEFERRED** | **200–500 ms** on high backlog | WebSocket/Gateway P2 protocol and replay owner | Larger protocol change involving reconnect, replay and backpressure. |
| Coalesce pure reasoning/delta observations | **PROPOSED WITH STRICT BARRIERS** | **100–400 ms** on high backlog | Agent event queue and P2 notification publisher | Never coalesce final, error, Tool, Task or Presentation barriers. |
| ACK/next-turn processing overlap | **CLOSED-ADJACENT — lifecycle stabilized by hx repairs; next-turn measured 0.4 ms after ACK today** | **50–150 ms** | P1/P2 ACK and successor-capture lifecycle | Mostly improves next-turn readiness, not first audible response. |
| PresentationUnit handoff tuning | **NOT A PRIMARY TARGET** | **<50 ms** | Conversation Runtime → presentation seam | Measured 0.3 ms today. |

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
On 2026-08-23 the P2 candidate was composed onto Hongxing lifecycle tip
`67381193a`; the remaining steps below start from that source.

1. ~~Repair the P2 Media observer~~ — **DONE: hx `c31e85ade` / D-094.** Original step: validate a complete `notification_batch`
   before effects, process valid items in order, let the final item establish
   TTS authority, and prove invalid batches grant zero partial authorization.
2. ~~Run deployed Live Voice A/B~~ — **PARTIALLY DONE: human acceptance passed (D-094); frozen-corpus off/on waterfall still open.** Original step: with the fixed short/medium/long prompts,
   optimization off/on, identical environment/config, successful completion,
   TTS/playout truth and a stage/total waterfall. This closes or rejects the
   P2 product candidate; the externally reported 46% alone grants no credit.
3. Preserve the measured LVL-09 target result of approximately 670–673 ms with
   2.757 ms A1/A2 target drift. A2 cancelled after first-start, so keep the
   1000 ms default until completed physical playout and reliability evidence
   close the broader Browser/manual-driver Gate.
4. Preserve the LVL-08 protocol repair but reject AUTO because 600/1000 ms
   pauses end early. Retain 1200 ms and do not run HIGH; reopen only with a new
   continuation-safe arbitration hypothesis.
5. Preserve the completed LVL-11 Agent first-delta baseline before attempting
   connection reuse, warm-up or prompt/history/tool reductions. Queue,
   connection, Provider and model subdivisions remain unclaimed until directly
   observed.
6. Keep stable-sentence stopped for short. Preserve the LVL-12 exact-prefix
   PASS and LVL-13 no-Browser real-Agent/real-TTS component acceptance for
   medium/long. Define product presentation authority, reconciliation and
   cancellation before Runtime/P2/Browser wiring, then run physical Gate C.
   Keep LVL-10/LVL-10L independent because they start after authoritative
   `chat.final`.
7. Consider authoritative P3 acknowledgements and fixed non-private phrase
   caching only when perceived Task latency is a product priority; neither
   shortens Task completion, and both retain Task/Presentation authority risk.
8. Revisit batch-32, push or coalescing only if the repaired Gate C waterfall
   demonstrates real P2 backlog.
9. Preserve LVL-10 as `INCONCLUSIVE` and LVL-10L as directional/formally
   incomplete; no Browser or product wiring follows either screen.
10. Treat native speech-to-speech as a strategic architecture study requiring a
   separate Registry/Tool/Task/presentation-authority decision.

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
- Hongxing's initial deployed bounded-P2 report remains external evidence for
  the approximately 46% number and the superseded authorization failure. The
  later source-bound `c31e85ade` follow-up closes the functional defect but
  does not retroactively create an off/on population for that percentage.
- [2026-08-24 SOTA latency review](../reviews/REALTIME_VOICE_SOTA_LATENCY_REVIEW_2026-08-24.md),
  including source-confidence labels, the one-round waterfall limits and the
  authority-compatible LVL-10 materiality question.
- `latency/pre-final-stable-agent-tts-screen` at `9600adbcf` owns the LVL-13
  runner and tests. The documentation hub owns the
  [LVL-13 result](../evidence/LVL13_PRE_FINAL_STABLE_AGENT_TTS_RESULT_2026-08-25.md)
  and [all-run appendix](../evidence/LVL13_PRE_FINAL_STABLE_AGENT_TTS_RUNS_2026-08-25.md).
- UPDATE 2026-08-23 additions:
  - Manual run archive: `lv-manual-simple-to-paris-20260824-a/`
    (validated run.json; generated report; browser.jsonl, 6 batches).
  - Driver/procedure: `<archive-root>/lv-driver.sh`;
    [LATENCY_PROBE_MANUAL_DRIVER](../runbooks/LATENCY_PROBE_MANUAL_DRIVER.md).
  - Current-source human/muted pilot:
    [MANUAL_MUTED_LATENCY_PILOT_20260824_37da36e68](../evidence/MANUAL_MUTED_LATENCY_PILOT_20260824_37da36e68.md).
  - Hongxing closures: `c31e85ade` (atomic batch observation, default-on,
    D-094, reviews), `1fec48027` (receipt/successor decoupling).
  - Lane probe reconciliation: `6f288de93`, `497831f58`.

## 11. Big-picture conclusion

The controlled checkpoint proves that bounded P2 delivery and successor-ACK
decoupling can coexist under its exact deterministic fixture. Hongxing source
`c31e85ade` and D-094 now own the accepted P2 default-on implementation and its
scoped human validation; the earlier authorization defect is closed for that
declared run, while frozen-corpus p50/p95 remains open. EOT/STT found at most
0.885 ms p50 removable tail and did not authorize a product change.
Stable-sentence measured only 177.2 ms p50 projected gain for the tested
workloads and stopped before product wiring. The distinct LVL-10 post-final TTS
screen then completed two 45/45 real-Provider populations with zero errors but
remained `INCONCLUSIVE` because each violated A1/A2 drift. Long completion
improved 20–24% while medium completion regressed. LVL-10L then passed a clean
12/12, 24-request v2 pilot with 6.93–7.75 seconds of derived 2100-character
completion gain, but its formal stopped before attempt artifacts on Hongxing's
direction. This is directional, not formal/product credit. Adaptive WebAudio
now has approximately 670–673 ms of measured same-workload target headroom with
2.757 ms A1/A2 target drift. A2 cancelled after first-start, so physical
acceptance remains incomplete and production stays at 1000 ms. Provider-native
Semantic VAD completes the protocol path and shows 684–734 ms EOT gain on two
cases, but AUTO is rejected for early EOT at 600/1000 ms and HIGH remains
unrun. The isolated Agent first-delta packet now has a 15/15 real-Agent
baseline: first-delta p50 is 523–592 ms, while delta→final p50 is approximately
9 ms for short, 1.68 s for medium and 3.52 s for long output. This is diagnostic
materiality, not proof of an immutable prefix or product latency credit.
LVL-12 subsequently proved exact-prefix materiality 10/10 for medium/long, and
LVL-13 accepted the next real-Agent/real-TTS component screen 30/30: digital
Agent→first-PCM p50 gain is 1.723 s / 52.510% medium and 3.422 s / 67.377% long.
The delta combines overlap and shorter first-prefix input; remaining-response
continuity, Runtime/P2, Browser and physical first-audible remain unmeasured.
The 2026-08-24 SOTA review introduced LVL-10 as a separate materiality question
from LVL-07. The completed screen grants no product credit: the current
full-final SSE route remains unchanged, Browser Lane C is closed, and the
[sanitized result](../evidence/LVL10_AUTHORITATIVE_FINAL_CHUNKED_TTS_RESULT_2026-08-24.md)
owns the original long-form secondary signal and its limits; the
[LVL-10L result](../evidence/LVL10L_LONG_FORM_CHUNKED_TTS_RESULT_2026-08-24.md)
owns the stopped completion-primary follow-up.
The current-source muted pilot adds partial localization at approximately
587.6 ms EOT/STT, 1,518.3 ms TTS-to-downlink and 728.0 ms schedule-to-start
diagnostic medians, but only two dialogue rounds completed. Four Task batches
cancelled, no true cancel batch exported, and driver terminal/profile/process
handling failed its workflow Gate. These figures do not close the baseline or
change any candidate status.
