# Agent first visible delta baseline — 2026-08-25

## 1. Decision and boundary

This is a real-Agent Gate-B timing diagnostic, not an optimization acceptance.
It measures the formal no-tools boundary
`agent.agent_started → first non-empty chat.delta → non-empty chat.final`.
It deliberately bypasses Browser, capture, STT, P1/P2 presentation, TTS and
playout. It therefore cannot claim physical first-audio or product end-to-end
latency.

The first visible delta is not automatically an immutable speakable prefix.
The measured `first_delta → final` interval is materiality available to a
future exact-prefix/stable-segmentation screen; it is not itself authorization
to speak provisional text.

## 2. Source and method

- JiuwenSwarm branch: `latency/agent-first-delta-probe`.
- JiuwenSwarm source: `f71a5d8300f621616030c4dafa608edaec6e46b0`.
- Installed Agent-Core source:
  `94e10cb6102c36fe78a64547957c0def97299273`.
- Runner: `scripts/live_voice/agent_first_delta_benchmark.py`.
- Project fixture: `/home/renan/openJiuwen-ai/live-voice-latency-fixture`.
- Population: one persistent real `AgentManager`, workloads executed in
  short → medium → long order, five sequential attempts per workload.
- Tool execution was disabled. The report records zero Tool, Task, history,
  STT, TTS and Browser effects.
- Prompt and Agent response content were used only in memory and were not
  serialized. The private report was created exclusively with mode `0600`.

The controlled workloads were the agreed short, medium and long prompts from
the inventory validation ladder. A separate one-attempt short smoke completed
before the formal population. The smoke measured 2123.701 ms to first delta,
13.336 ms from first delta to final and 2137.037 ms from Agent start to final.

## 3. Population result

All 15/15 calls completed. With five values, nearest-rank P95 is the maximum;
it is useful as a small-population diagnostic and not a production percentile.

| Workload | Agent start → first delta p50 / p95 | First delta → final p50 / p95 | Agent start → final p50 / p95 |
|---|---:|---:|---:|
| Short | 522.856 / 1337.260 ms | 8.779 / 8.853 ms | 531.645 / 1345.974 ms |
| Medium | 543.185 / 682.479 ms | 1676.287 / 1699.966 ms | 2215.234 / 2359.441 ms |
| Long | 591.914 / 742.521 ms | 3518.228 / 3637.023 ms | 4158.856 / 4260.749 ms |

The short result confirms Hongxing's observation: for a city-name-only answer,
the first delta precedes final by only about 9 ms at p50, so pre-final sentence
segmentation has effectively no useful latency window. Medium and long outputs
show large pre-final windows, approximately 1.68 s and 3.52 s at p50. Those
windows justify the next exact-prefix/stability materiality screen, but do not
prove that a semantically complete immutable sentence exists at the first
delta.

The population also shows a warm-state distinction. Its first short call took
1337.260 ms to first delta, while the remaining short calls were approximately
516–542 ms. Queueing, request preparation, connection/network and model
first-token time are still aggregated inside this measurement and remain the
next decomposition target.

## 4. Artifact binding

- Content-free population report:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/agent-first-delta-20260825/population-f71a5d8300f621616030c4dafa608edaec6e46b0.json`
  (`SHA-256 c81fd7fcbcdc593d26f8ca30dd169164bc1c43c7f3998c59f944e19775fc16a4`).
- Content-free smoke report:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/agent-first-delta-20260825/smoke-f71a5d8300f621616030c4dafa608edaec6e46b0.json`
  (`SHA-256 f2a4dd4caae055f107a6e9207236999207a629429746e5537dadfc960125b446`).
- The verbose local log is diagnostic-only and may contain runtime metadata;
  it is not a shareable or credited evidence artifact.

## 5. Next gate

Keep the first-delta instrumentation default-off. Before changing product
behaviour, run an exact-prefix/stable-segmentation screen on medium and long
responses and require that every emitted prefix is byte-identical to the same
prefix in `chat.final`. Separately instrument Agent request preparation,
queueing, connection/network and Provider/model first-token boundaries; do not
infer their shares from this aggregate interval.
