# LVL-13 pre-final stable Agent-to-TTS result — 2026-08-25

## Decision

**ACCEPTED — NO-BROWSER REAL-AGENT/REAL-TTS COMPONENT CANDIDATE. NO PRODUCT,
BROWSER, PHYSICAL FIRST-AUDIBLE OR `PresentationUnit` CREDIT.**

The experiment demonstrates material digital first-PCM headroom when the first
conservative exact prefix is synthesized while the Agent continues producing
the final response. It does not authorize speaking that prefix in Live Voice:
the product authority, cancellation, reconciliation, presentation and physical
playout contract remains a separate design and acceptance boundary.

## Source and boundary

- Branch: `latency/pre-final-stable-agent-tts-screen`.
- JiuwenSwarm source:
  `9600adbcf214a6bbc9dd6e08db4a8c59697854d3`.
- Installed Agent-Core:
  `94e10cb6102c36fe78a64547957c0def97299273`.
- Boundary: real formal no-tools Agent start to real Speech Provider first PCM.
- Workloads: medium water-cycle response and long Hangzhou response.
- Population: one excluded Agent+TTS warm-up, followed by five sequential
  attempts for each A1/B/A2 arm and each workload: 30 measured Agent calls and
  30 measured TTS calls.
- A1/A2: wait for `chat.final`, then synthesize the complete final response.
- B: synthesize the first conservative exact-prefix candidate concurrently
  while continuing to observe and reconcile the final Agent response.
- P95 is nearest rank over five values and is not a production percentile.

The declared materiality gates were at least 400 ms and 10% gain versus the
interpolated A1/A2 p50. The validity gates required A1/A2 p50 drift no greater
than both 400 ms and 20%.

## Implementation method

The validation-only runner
`scripts/live_voice/pre_final_stable_agent_tts_screen.py` reuses the formal
no-tools Agent harness, the LVL-12 conservative stable-prefix policy and the
real `OpenAIStreamingSpeechProvider`. It does not call the Live Voice product
Runtime or simulate Browser events.

For each attempt it performs the following sequence:

1. reserve and commit one isolated Agent round with tools disabled;
2. mark `agent_started` from the Agent latency-probe hook;
3. feed ordered `chat.delta` events into the punctuation-plus-visible-
   lookahead policy until the first conservative candidate appears;
4. commit that candidate only inside validation state and continue observing
   Tool/error/final events;
5. in B, dispatch real streaming TTS immediately for the candidate; in A1/A2,
   wait for `chat.final` and dispatch real streaming TTS for the complete final;
6. stop the primary clock on the first valid non-empty PCM chunk, continue to
   Provider completion, close the Provider and require a clean snapshot;
7. reconcile the candidate against `chat.final`, require `exact_prefix`, a
   completed Agent terminal event, one Agent call, one TTS call and zero
   forbidden effects.

The runner uses one persistent `AgentManager`, but a fresh TTS Provider object
for each attempt. Exactly one medium A1-style Agent/full-final-TTS round warms
the process and external dependency path before measurement and is separately
counted as an excluded call; it does not reuse the warm-up TTS connection.
Attempts then run sequentially in the fixed order
`A1 → B → A2`, medium then long, five times per arm/workload.

The causal comparison is:

```text
A1: Agent start → chat.final → full-final TTS request → first PCM
B:  Agent start → exact-prefix candidate → prefix TTS request → first PCM
                              └──────── Agent continues → chat.final/reconcile
A2: Agent start → chat.final → full-final TTS request → first PCM
```

The interpolated control is `(A1 p50 + A2 p50) / 2`. Gain is interpolated
control minus B p50. A1/A2 drift must pass both the absolute and relative
limits before a B gain can receive credit.

## Formal result

### Agent stages, p50 / nearest-rank p95

Candidate timing is measured in all arms for comparability, although it
triggers TTS only in B.

| Workload / arm | Agent→candidate | Candidate→final | Agent→final |
|---|---:|---:|---:|
| Medium A1 | 696.904 / 741.281 ms | 1531.904 / 1536.714 ms | 2227.543 / 2277.995 ms |
| Medium B | 634.413 / 880.755 ms | 1531.590 / 1531.746 ms | 2166.120 / 2398.903 ms |
| Medium A2 | 682.965 / 970.342 ms | 1523.338 / 1588.952 ms | 2219.224 / 2478.408 ms |
| Long A1 | 700.731 / 810.987 ms | 3354.354 / 3556.889 ms | 4055.085 / 4216.150 ms |
| Long B | 692.352 / 710.692 ms | 3240.800 / 3955.313 ms | 3938.775 / 4631.554 ms |
| Long A2 | 693.380 / 751.309 ms | 3299.374 / 3641.242 ms | 4050.683 / 4342.200 ms |

### TTS and primary digital total, p50 / nearest-rank p95

The runner report stores p50 for both TTS sub-stages and p50/p95 for the
primary total. TTS p95 below is recomputed directly from the five retained
attempt rows using the same nearest-rank method.

| Workload / arm | Dispatch→request | Request→first PCM | Agent→first PCM |
|---|---:|---:|---:|
| Medium A1 | 0.109 / 0.112 ms | 918.076 / 1093.644 ms | 3140.796 / 3371.752 ms |
| Medium B | 0.065 / 0.092 ms | 868.886 / 994.725 ms | 1558.399 / 1875.545 ms |
| Medium A2 | 0.128 / 0.156 ms | 1022.340 / 1652.024 ms | 3422.333 / 3857.015 ms |
| Long A1 | 0.211 / 0.293 ms | 982.608 / 1135.380 ms | 4981.692 / 5351.788 ms |
| Long B | 0.038 / 0.039 ms | 970.890 / 1009.355 ms | 1657.019 / 1707.368 ms |
| Long A2 | 0.223 / 0.233 ms | 1062.597 / 1510.615 ms | 5177.037 / 5412.884 ms |

### Stage-by-stage A/B/A p50 deltas

The control column below is the mean of the A1 and A2 stage p50 values. A
positive delta means B was faster; a negative delta means B was slower. Only
the primary Agent→first-PCM delta is the predeclared acceptance metric. Other
deltas help localize variation but are not independent causal gains.

| Stage | Medium control / B / delta | Long control / B / delta | Reading |
|---|---:|---:|---|
| Agent→candidate | 689.935 / 634.413 / **+55.522 ms** | 697.055 / 692.352 / **+4.703 ms** | Candidate detection timing was broadly stable across arms. |
| Candidate→final | 1527.621 / 1531.590 / **−3.969 ms** | 3326.864 / 3240.800 / **+86.064 ms** | Available overlap window; not an independently removable wait. |
| Agent→final | 2223.383 / 2166.120 / **+57.264 ms** | 4052.884 / 3938.775 / **+114.109 ms** | Cross-arm Agent/model variation; B does not make final generation faster by contract. |
| TTS dispatch→request | 0.118 / 0.065 / **+0.053 ms** | 0.217 / 0.038 / **+0.179 ms** | Local scheduling is negligible. |
| TTS request→first PCM | 970.208 / 868.886 / **+101.322 ms** | 1022.602 / 970.890 / **+51.712 ms** | B sends less text; this is not pure connection/provider acceleration. |
| **Agent→first PCM** | 3281.565 / 1558.399 / **+1723.166 ms** | 5079.365 / 1657.019 / **+3422.345 ms** | Accepted digital component gain from changing the TTS trigger/input boundary. |

Stage p50 deltas are deliberately not added: medians of overlapping intervals
and medians of their sums are not algebraically additive.

The complete 30-row formal population and a field-by-field reading guide are
in the [LVL-13 run appendix](LVL13_PRE_FINAL_STABLE_AGENT_TTS_RUNS_2026-08-25.md).

### Headroom and acceptance gates

| Workload | Interpolated control p50 | B p50 | Measured gain | Relative gain | A1/A2 drift | Gate |
|---|---:|---:|---:|---:|---:|---|
| Medium | 3281.565 ms | 1558.399 ms | **1723.166 ms** | **52.510%** | 281.537 ms / 8.964% | PASS |
| Long | 5079.365 ms | 1657.019 ms | **3422.345 ms** | **67.377%** | 195.345 ms / 3.921% | PASS |

All 30 exact slots completed, every B candidate reconciled as an exact prefix,
and all forbidden Tool, Task, history, STT, Browser, product-downlink and
playout effects remained zero. Median dispatch-to-request overhead in B was
0.065 ms medium and 0.038 ms long, so the measured gain was not created by a
hidden scheduling delay before the Provider request.

## Pilot and warm-up rationale

The initial six-slot pilot at `44bb8b6ff` was functionally complete but was
rejected for causal credit because cold/warm A1/A2 drift exceeded the declared
validity gate. Source `9600adbcf` added exactly one excluded A1-style medium
Agent/full-final-TTS warm-up using the same persistent `AgentManager`. The warm
pilot then passed both workloads, and the same declared warm-up was used for
the formal population. The rejected cold pilot remains diagnostic and is not
pooled with the accepted formal result.

- Rejected cold pilot SHA-256:
  `867fbe1a6be5b44563d9d8a45b1b88eb6f42775a820949660b3a910612af2969`.
- Passing warm pilot SHA-256:
  `9e7e3a8abc97163ea425b199a5ccfb50596a8090332192ad1288b3e175429e0e`.

| Run | Medium A1/B/A2 p50 | Medium gain / drift | Long A1/B/A2 p50 | Long gain / drift | Decision |
|---|---:|---:|---:|---:|---|
| Cold pilot | 5690.616 / 2331.597 / 3234.473 ms | 2130.947 ms; drift 2456.143 ms / 75.936% | 6097.536 / 2032.301 / 5493.982 ms | 3763.458 ms; drift 603.554 ms / 10.986% | Rejected: control drift |
| Warm pilot | 2742.154 / 1961.339 / 2791.153 ms | 805.314 ms; drift 48.999 ms / 1.787% | 5299.449 / 1571.842 / 5508.581 ms | 3832.173 ms; drift 209.132 ms / 3.946% | Pilot pass |
| Formal | 3140.796 / 1558.399 / 3422.333 ms | 1723.166 ms; drift 281.537 ms / 8.964% | 4981.692 / 1657.019 / 5177.037 ms | 3422.345 ms; drift 195.345 ms / 3.921% | Component accepted |

## Artifact and review binding

- Formal private content-free report:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/pre-final-stable-agent-tts-20260825/formal-9600adbcf214a6bbc9dd6e08db4a8c59697854d3.json`.
- SHA-256:
  `712eab619ece2e59f14c7b87d154cb2f4b8e46a5b232c971c5606ede31c271e9`.
- File mode: `0600`.
- Private checksum manifest:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/pre-final-stable-agent-tts-20260825/SHA256SUMS`.
- Sanitized attempt-level reading route:
  [LVL-13 run appendix](LVL13_PRE_FINAL_STABLE_AGENT_TTS_RUNS_2026-08-25.md).
- Independent formal artifact audit:
  `/home/renan/openJiuwen-ai/live-voice-latency-reviews/LVL13_FORMAL_ARTIFACT_AUDIT_2026-08-25.md`, `PASS C0/I0/M0`.
- The audit independently verified source/ref binding, exact slot order,
  call/warm-up accounting, forbidden effects, p50/p95 values, drift gates and
  the final `CANDIDATE_ACCEPTED` decision.

## Interpretation and next gate

This result answers a component question: for medium and long responses, real
TTS can begin producing PCM materially earlier from a retrospectively exact
prefix than from the complete final response. It is not a physical end-to-end
result. It excludes STT, Runtime/P2 presentation authority, Browser transport,
WebAudio buffering, device playback, barge-in and user-perceived first audio.

The measured delta is the combined effect of overlapping TTS with continued
Agent generation and sending a shorter first-prefix TTS request; this screen
does not attribute the gain between those two mechanisms. Agent response text
can also vary across arms even with the same prompts and configuration. A/B/A
control drift bounds timing instability, but does not make generated texts
identical. Finally, B measures only first-prefix PCM and does not establish the
latency, ordering or continuity of synthesizing the remaining final response.

Before product wiring, define and review how a pre-final prefix can become an
immutable authoritative `PresentationUnit`, how later Agent output reconciles
without duplicate speech, and how cancellation/failure remains fail-closed.
Only then may a deployed Gate-C A/B/A run measure Browser first-start,
audibility, underrun/rebuffer, interruption and final semantic integrity.
