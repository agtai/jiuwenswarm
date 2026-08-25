# LVL-12 pre-final stable segmentation result — 2026-08-25

## Decision

**PASS — EXACT-PREFIX MATERIALITY; READY FOR A SEPARATE NO-BROWSER TTS
SCREEN. NO PRODUCT OR SPEECH AUTHORITY.**

The screen proves that a conservative punctuation-plus-visible-lookahead
prefix can be observed materially before `chat.final` and later reconcile as
its exact UTF-8 prefix for the declared medium/long workloads. It does not make
that prefix authoritative at observation time and does not wire a
`PresentationUnit`, TTS, Browser or product route.

## Source and boundary

- Branch: `latency/pre-final-stable-segmentation-screen`.
- JiuwenSwarm source: `ea64751200f725103b757430cde195d0050e6b5c`.
- Installed Agent-Core:
  `94e10cb6102c36fe78a64547957c0def97299273`.
- Boundary: real formal no-tools Agent
  `agent.agent_started → first conservative candidate → chat.final`.
- Population: five sequential medium and five sequential long attempts under
  one persistent `AgentManager`.
- Excluded effects: Tool, Task, history, STT, TTS, Browser, product downlink
  and audio playout; all remain zero in the report.
- P95 uses nearest rank over five values and is not a production percentile.

## Result

| Workload | Completed | Agent→candidate p50 / p95 | Candidate→final p50 / p95 | Agent→final p50 / p95 |
|---|---:|---:|---:|---:|
| Medium | 5/5 | 657.947 / 1435.454 ms | 1587.308 / 1604.963 ms | 2259.234 / 3023.703 ms |
| Long | 5/5 | 707.935 / 713.492 ms | 3573.381 / 3655.636 ms | 4281.316 / 4369.129 ms |

Both workloads pass the predeclared 500 ms candidate→final p50 materiality
gate. Every successful attempt reconciled with disposition `exact_prefix` and
terminal outcome `completed`.

## Diagnostic run and repair

The first population at `e59f7efdb` retained all ten slots. Medium passed 5/5
with candidate→final p50 1617.166 ms; long failed 0/5 and the run correctly
returned `INTEGRITY_FAILED`. The runner continued feeding every post-candidate
Agent delta into the historical policy until its bounded 256-event ledger was
exhausted.

Commit `ea6475120` fixes the screen without raising that safety bound. Once the
first candidate is committed inside validation state, later deltas are ignored
by the candidate detector; Tool/error/final events remain observed and
`chat.final` still performs exact-prefix reconciliation. A deterministic
300-delta-tail test covers the defect. The focused policy/screen/probe suite
passes 36/36 with Ruff, compile and diff-check PASS, and the scoped real-run fix
review is `C0/I0/M0`.

## Artifact binding

- Accepted private content-free report:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/pre-final-stable-segmentation-20260825/population-v2-ea64751200f725103b757430cde195d0050e6b5c.json`.
- SHA-256:
  `a78295c33043f02c906e6c343506d42d367a2e43246c9530acbab5477150a7a9`.
- File mode: `0600`.
- The prior `e59f7efdb` report is retained as a rejected diagnostic and is not
  pooled with the accepted v2 population.

## Next gate

Build a separate no-Browser real Agent→TTS A/B/A screen. Compare current
full-final TTS start against first exact-prefix-candidate TTS start while
requiring exact spoken-prefix integrity, Provider cleanup, bounded cancellation
and zero product effects. Do not wire the Conversation Runtime, P2 or Browser
until that component screen passes and a separate product-authority design is
accepted.
