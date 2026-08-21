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

- Runner commit: `e2773bec2740e933721d1f598e06978b5b476860`.
- Product base: `465a21625bf253729f00b7c84e6cc08e9bd746a2`.
- Corpus ID: `vad-en-v1`.
- Private manifest SHA-256:
  `44c1c1d12363fd036f1fd647e0c1af185ae649ac8b0dcb4e092e2cd66e7c38c2`.
- Immutable source WAV SHA-256:
  `e37d2f1eb21ac3bfe61048b3e4f246c2775432b606742dc0bdbcaa57f84dde3c`.
- Provider/model labels: `openai` /
  `OpenAIStreamingSpeechProvider` /
  `gpt-4o-mini-transcribe-2025-12-15`.
- Pilot: `vad-eot-tier2-pilot-20260821t031949`, one attempt per
  case/configuration.
- Formal: `vad-eot-tier2-formal-20260821t032202`, five attempts per
  case/configuration.

The private builder replaced one frozen low-energy boundary with exact total
pauses of 0/300/600/1000 ms and retained the same audio on both sides. The
runner sent PCM through the existing Provider adapter as contiguous 20 ms,
48 kHz frames paced to absolute monotonic deadlines. The order was fixed as
A1/1200 → E1/900 → E2/800 → A2/1200. A numeric latency sample required one
exact started/stopped/committed/final turn, complete normalized transcript,
valid pacing and clean Provider cleanup.

Earlier private runs retain historical diagnostic value but receive no current
integration credit. They exposed
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
| A1 / 1200 | no pause | 5/5 | 0 | 1507.8 | 1584.5 |
| A1 / 1200 | 300 ms | 5/5 | 0 | 1505.6 | 1529.4 |
| A1 / 1200 | 600 ms | 5/5 | 0 | 1528.1 | 1574.7 |
| A1 / 1200 | 1000 ms | 5/5 | 0 | 1507.8 | 1532.0 |
| E1 / 900 | no pause | 5/5 | 0 | 1221.9 | 1222.9 |
| E1 / 900 | 300 ms | 5/5 | 0 | 1197.1 | 1197.6 |
| E1 / 900 | 600 ms | 5/5 | 0 | 1218.7 | 1242.7 |
| E1 / 900 | 1000 ms | 0/5 | 5 | — | — |
| E2 / 800 | no pause | 5/5 | 0 | 1081.5 | 1113.6 |
| E2 / 800 | 300 ms | 5/5 | 0 | 1080.1 | 1107.9 |
| E2 / 800 | 600 ms | 5/5 | 0 | 1103.1 | 1114.1 |
| E2 / 800 | 1000 ms | 0/5 | 5 | — | — |
| A2 / 1200 | no pause | 5/5 | 0 | 1498.8 | 1509.8 |
| A2 / 1200 | 300 ms | 5/5 | 0 | 1501.5 | 1529.9 |
| A2 / 1200 | 600 ms | 5/5 | 0 | 1520.6 | 1526.6 |
| A2 / 1200 | 1000 ms | 5/5 | 0 | 1504.2 | 1516.1 |

Aggregate outcomes were A1 20/20, E1 15/20, E2 15/20 and A2 20/20.
The ten lower-threshold failures were all `EARLY_EOT` on the exact 1000 ms
pause. All 80 attempts had valid pacing and clean Provider
cleanup. Unknown/invalid counts were zero. Agent, Tool, Task, P2, TTS, history
and Browser forbidden-effect counters were all zero.

## Interpretation and remaining boundary

The successful-case p50 fell by roughly 285–412 ms under 900/800 ms, but that
gain is invalid as a fixed-default optimization because turn integrity fell to
15/20 for each candidate. A1/A2 both preserved 20/20 and had closely aligned
p50 values, so the rejection is not caused by an unstable control.

No product source or `ServerVadConfig.silence_duration_ms=1200` default changed.
The raw mode-600 reports and WAVs remain outside Git. Independent Tier-2 review
found and closed the runner's timeout, pacing, corpus/TOCTOU, artifact,
privacy, model-identity and test-matrix findings before this credited pair was
executed. No Browser or product acceptance is inferred.
