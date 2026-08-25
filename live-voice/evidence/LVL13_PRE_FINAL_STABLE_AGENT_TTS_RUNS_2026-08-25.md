# LVL-13 pre-final stable Agent-to-TTS run appendix — 2026-08-25

## Purpose

This appendix is the sanitized, human-readable index of every retained LVL-13
run and every attempt in the accepted formal population. The
[result document](LVL13_PRE_FINAL_STABLE_AGENT_TTS_RESULT_2026-08-25.md) owns
the decision, method and interpretation. Private JSON is retained outside Git
under:

`/home/renan/openJiuwen-ai/live-voice-latency-runs/pre-final-stable-agent-tts-20260825/`.

All timings are milliseconds measured on one monotonic process clock. No
prompt text, Agent response, audio payload, credential or Provider URL is
retained in the reports.

## Retained runs

| Run | Source | Population | A1/B/A2 medium p50 | A1/B/A2 long p50 | Decision | SHA-256 |
|---|---|---:|---:|---:|---|---|
| Cold pilot | `44bb8b6ff` | 6 measured; no warm-up | 5690.616 / 2331.597 / 3234.473 | 6097.536 / 2032.301 / 5493.982 | `CANDIDATE_REJECTED`: control drift | `867fbe1a6be5b44563d9d8a45b1b88eb6f42775a820949660b3a910612af2969` |
| Warm pilot | `9600adbcf` | 6 measured + 1 excluded warm-up | 2742.154 / 1961.339 / 2791.153 | 5299.449 / 1571.842 / 5508.581 | `PILOT_PASS` | `9e7e3a8abc97163ea425b199a5ccfb50596a8090332192ad1288b3e175429e0e` |
| Formal | `9600adbcf` | 30 measured + 1 excluded warm-up | 3140.796 / 1558.399 / 3422.333 | 4981.692 / 1657.019 / 5177.037 | `CANDIDATE_ACCEPTED` | `712eab619ece2e59f14c7b87d154cb2f4b8e46a5b232c971c5606ede31c271e9` |

The cold pilot completed functionally, but its A1/A2 p50 drift was
2456.143 ms / 75.936% medium and 603.554 ms / 10.986% long. It is retained as
diagnostic evidence and contributes no gain credit. The declared warm-up
removed this cold/warm validity problem before the formal population.

## How to read the report-level result

| JSON field | Meaning |
|---|---|
| `status` | Population integrity only. `PASS` means the exact required slots/calls/prefix outcomes completed; it does not mean the optimization passed its latency gates. |
| `decision` | Experiment disposition after integrity, control-drift and materiality gates. The formal accepted value is `CANDIDATE_ACCEPTED`. |
| `arm_contract` | TTS trigger for each arm: A1/A2 use `chat_final`; B uses `exact_prefix_candidate`. |
| `attempts` | Every measured slot, including failed slots if any. Failures are never removed from the denominator. |
| `summaries` | Per-workload A1/B/A2 p50/p95 plus interpolated control, gain, relative gain and drift. |
| `authorized_agent_calls` / `authorized_tts_calls` | Measured call totals. The formal report requires 30/30. |
| `excluded_warmup_*` | Calls made by the single declared warm-up and intentionally excluded from measured statistics. |
| `forbidden_effects` | Tool, Task, history, STT, Browser and product-side effects; every counter must remain zero. |
| `browser_exercised` / `product_wiring_exercised` | Both are false, preventing accidental product or physical credit. |
| `payload_retained` | False: prompts, generated Agent text and PCM content are not stored in the report. |

This distinction explains why the cold pilot has `status=PASS` but
`decision=CANDIDATE_REJECTED`: all six slots worked, yet A1/A2 timing drift made
the causal comparison invalid. Functional completion and optimization
acceptance are intentionally separate.

## How to read one attempt

| Field | Timestamp subtraction | Meaning |
|---|---|---|
| `agent_to_candidate_ms` | candidate observed − Agent started | Time until the conservative punctuation-plus-lookahead policy finds the first candidate. It is measured in every arm, but triggers TTS only in B. |
| `candidate_to_final_ms` | `chat.final` − candidate observed | Window in which B can overlap TTS with continued Agent generation. It is not itself saved latency. |
| `agent_to_final_ms` | `chat.final` − Agent started | Complete Agent generation time for the attempt. |
| `tts_dispatch_to_request_ms` | Provider request start − logical TTS dispatch | Local scheduling overhead before entering the Provider request. |
| `tts_request_to_first_pcm_ms` | first non-empty PCM − Provider request start | Real Speech Provider first-PCM latency for the exact text sent by that arm. |
| `agent_to_first_pcm_ms` | first PCM − Agent started | Primary digital result. In B it equals Agent→candidate + dispatch + Provider first PCM; in A1/A2 it equals Agent→final + dispatch + Provider first PCM. |

`agent_to_candidate_ms`, `candidate_to_final_ms` and `agent_to_final_ms` describe
the same Agent timeline and therefore overlap. They must not be added together
as independent costs. Likewise, the LVL-13 primary result ends at PCM arrival;
it contains no Browser transport, WebAudio scheduling or physical audibility.

## Formal population: every measured attempt

| Arm | Workload | Attempt | Agent→candidate | Candidate→final | Agent→final | Dispatch→request | Request→first PCM | Agent→first PCM |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A1 | medium | 1 | 668.311 | 1532.483 | 2200.794 | 0.111 | 918.076 | 3118.982 |
| A1 | medium | 2 | 637.746 | 1531.904 | 2169.651 | 0.109 | 627.750 | 2797.510 |
| A1 | medium | 3 | 741.281 | 1536.714 | 2277.995 | 0.112 | 1093.644 | 3371.752 |
| A1 | medium | 4 | 696.904 | 1530.639 | 2227.543 | 0.106 | 913.147 | 3140.796 |
| A1 | medium | 5 | 722.434 | 1531.470 | 2253.904 | 0.104 | 1021.058 | 3275.066 |
| A1 | long | 1 | 659.261 | 3556.889 | 4216.150 | 0.258 | 1135.380 | 5351.788 |
| A1 | long | 2 | 695.997 | 3464.277 | 4160.273 | 0.211 | 781.127 | 4941.611 |
| A1 | long | 3 | 810.987 | 3187.916 | 3998.902 | 0.182 | 982.608 | 4981.692 |
| A1 | long | 4 | 717.753 | 3206.374 | 3924.127 | 0.175 | 1078.695 | 5002.998 |
| A1 | long | 5 | 700.731 | 3354.354 | 4055.085 | 0.293 | 783.753 | 4839.131 |
| B | medium | 1 | 634.413 | 1531.707 | 2166.120 | 0.072 | 645.714 | 1280.199 |
| B | medium | 2 | 629.957 | 1531.746 | 2161.702 | 0.037 | 931.270 | 1561.263 |
| B | medium | 3 | 695.005 | 1531.590 | 2226.595 | 0.092 | 863.302 | 1558.399 |
| B | medium | 4 | 633.668 | 1523.767 | 2157.436 | 0.038 | 868.886 | 1502.592 |
| B | medium | 5 | 880.755 | 1518.148 | 2398.903 | 0.065 | 994.725 | 1875.545 |
| B | long | 1 | 692.352 | 3163.260 | 3855.612 | 0.039 | 475.693 | 1168.085 |
| B | long | 2 | 654.598 | 3393.185 | 4047.784 | 0.038 | 948.325 | 1602.961 |
| B | long | 3 | 710.692 | 3211.374 | 3922.066 | 0.038 | 970.890 | 1681.620 |
| B | long | 4 | 697.976 | 3240.800 | 3938.775 | 0.037 | 1009.355 | 1707.368 |
| B | long | 5 | 676.241 | 3955.313 | 4631.554 | 0.036 | 980.741 | 1657.019 |
| A2 | medium | 1 | 810.885 | 1588.952 | 2399.837 | 0.156 | 1022.340 | 3422.333 |
| A2 | medium | 2 | 970.342 | 1508.066 | 2478.408 | 0.156 | 996.079 | 3474.643 |
| A2 | medium | 3 | 676.484 | 1542.740 | 2219.224 | 0.105 | 1106.621 | 3325.951 |
| A2 | medium | 4 | 682.965 | 1521.898 | 2204.863 | 0.128 | 1652.024 | 3857.015 |
| A2 | medium | 5 | 654.334 | 1523.338 | 2177.672 | 0.102 | 747.475 | 2925.248 |
| A2 | long | 1 | 637.266 | 3264.804 | 3902.070 | 0.199 | 1510.615 | 5412.884 |
| A2 | long | 2 | 700.958 | 3641.242 | 4342.200 | 0.223 | 1062.597 | 5405.020 |
| A2 | long | 3 | 751.309 | 3299.374 | 4050.683 | 0.212 | 1020.968 | 5071.862 |
| A2 | long | 4 | 678.492 | 3444.138 | 4122.629 | 0.233 | 1054.174 | 5177.037 |
| A2 | long | 5 | 693.380 | 3230.766 | 3924.145 | 0.231 | 1194.606 | 5118.982 |

Every row completed with `prefix_exact=true`, one authorized Agent call, one
authorized TTS call and zero forbidden effects. Attempt numbers above are
one-based for readers; the JSON stores `attempt_index` from zero through four.

## Interpretation limits

- A1 and A2 synthesize the complete `chat.final`; B synthesizes only the first
  exact-prefix candidate. The primary gain therefore combines overlap with a
  shorter initial TTS input and does not isolate either contribution.
- The same prompts and configuration were reused, but Agent response text can
  differ across arms. A1/A2 drift bounds timing instability; it does not make
  generated content identical.
- The formal run measures first PCM only. It does not measure synthesis or
  playback of the remaining response, continuity between units, duplicate
  speech, barge-in or physical end-to-end latency.
- Nearest-rank P95 over five values is the maximum of that small population,
  not a production-tail estimate.
