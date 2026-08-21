# VAD/EOT no-Browser causal screening result

Date: 2026-08-21

## Decision

`FIXED_THRESHOLD_REJECTED` — retain the product default of 1200 ms. Neither
900 ms nor 800 ms preserved one complete turn for every controlled pause case,
so their lower successful-case latency cannot authorize a global default
change. Route any further VAD work to a semantic/adaptive design with the same
commit and fence contract.

This is real-Provider component evidence only. It contains no Browser,
microphone, Gateway media socket, Agent, Tool, Task, P2, TTS, playout or
end-to-end product-path measurement.

## Exact source and method

- Runner commit: `048f944e4ff8bc88f0b006fe50731b161d67f485`.
- Product base: `465a21625bf253729f00b7c84e6cc08e9bd746a2`.
- Corpus ID: `vad-en-v1`.
- Private manifest SHA-256:
  `f93937dcca63d9fb1ec33aa57a2aeb656c12d757c302bc96aa9e6ef7dc0ec5f4`.
- Immutable source WAV SHA-256:
  `e37d2f1eb21ac3bfe61048b3e4f246c2775432b606742dc0bdbcaa57f84dde3c`.
- Provider/model labels: `openai` /
  `OpenAIStreamingSpeechProvider` / `gpt-4o-mini-transcribe`.
- Pilot: `vad-eot-pilot-20260821t013116`, one attempt per case/configuration.
- Formal: `vad-eot-formal-20260821t013344`, five attempts per
  case/configuration.

The private builder replaced one frozen low-energy boundary with exact total
pauses of 0/300/600/1000 ms and retained the same audio on both sides. The
runner sent PCM through the existing Provider adapter as contiguous 20 ms,
48 kHz frames paced to absolute monotonic deadlines. The order was fixed as
A1/1200 → E1/900 → E2/800 → A2/1200. A numeric latency sample required one
exact started/stopped/committed/final turn, complete normalized transcript,
valid pacing and clean Provider cleanup.

Two preliminary private runs received no decision credit. The first exposed
that low-level phone noise was being treated as spoken tail; the second exposed
that the declared pause had been added to, rather than substituted for, the
recording's existing silence. Both defects were reproduced in RED tests,
corrected, and the corpus was rebuilt under a new hash before the credited
pilot/formal pair.

## Formal result

All timing values below are milliseconds and include only successful attempts.
`p95` is nearest-rank.

| Configuration | Case | Success | Failed | EOT p50 | EOT p95 |
|---|---|---:|---:|---:|---:|
| A1 / 1200 | no pause | 5/5 | 0 | 1503.5 | 1561.2 |
| A1 / 1200 | 300 ms | 5/5 | 0 | 1502.7 | 1510.1 |
| A1 / 1200 | 600 ms | 5/5 | 0 | 1521.6 | 1544.8 |
| A1 / 1200 | 1000 ms | 5/5 | 0 | 1501.4 | 1516.7 |
| E1 / 900 | no pause | 5/5 | 0 | 1220.3 | 1223.2 |
| E1 / 900 | 300 ms | 4/5 | 1 | 1199.3 | 1231.4 |
| E1 / 900 | 600 ms | 5/5 | 0 | 1219.7 | 1231.6 |
| E1 / 900 | 1000 ms | 0/5 | 5 | — | — |
| E2 / 800 | no pause | 5/5 | 0 | 1078.2 | 1080.5 |
| E2 / 800 | 300 ms | 4/5 | 1 | 1104.1 | 1133.8 |
| E2 / 800 | 600 ms | 5/5 | 0 | 1099.6 | 1135.5 |
| E2 / 800 | 1000 ms | 0/5 | 5 | — | — |
| A2 / 1200 | no pause | 5/5 | 0 | 1500.4 | 1545.8 |
| A2 / 1200 | 300 ms | 5/5 | 0 | 1498.3 | 1568.4 |
| A2 / 1200 | 600 ms | 5/5 | 0 | 1520.9 | 1524.9 |
| A2 / 1200 | 1000 ms | 5/5 | 0 | 1504.4 | 1587.0 |

Aggregate outcomes were A1 20/20, E1 14/20, E2 14/20 and A2 20/20.
The 12 lower-threshold failures were ten `EARLY_EOT` and two
`TRANSCRIPT_INCOMPLETE`. All 80 attempts had valid pacing and clean Provider
cleanup. Unknown/invalid counts were zero. Agent, Tool, Task, P2, TTS, history
and Browser forbidden-effect counters were all zero.

## Interpretation and remaining boundary

The successful-case p50 fell by roughly 280–425 ms under 900/800 ms, but that
gain is invalid as a fixed-default optimization because turn integrity fell to
14/20 for each candidate. A1/A2 both preserved 20/20 and had closely aligned
p50 values, so the rejection is not caused by an unstable control.

No product source or `ServerVadConfig.silence_duration_ms=1200` default changed.
The raw mode-600 reports and WAVs remain outside Git. A separate independent
Tier-2 review of the runner/evidence remains desirable before integration; the
conservative no-change decision does not depend on claiming product acceptance.
