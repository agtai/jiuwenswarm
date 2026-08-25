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

## Formal result

| Workload / arm | Agent→first PCM p50 / p95 | Agent→candidate p50 / p95 | Candidate→final p50 / p95 | TTS request→first PCM p50 |
|---|---:|---:|---:|---:|
| Medium A1 | 3140.796 / 3371.752 ms | — | — | — |
| Medium B | 1558.399 / 1875.545 ms | 634.413 / 880.755 ms | 1531.590 / 1531.746 ms | 868.886 ms |
| Medium A2 | 3422.333 / 3857.015 ms | — | — | — |
| Long A1 | 4981.692 / 5351.788 ms | — | — | — |
| Long B | 1657.019 / 1707.368 ms | 692.352 / 710.692 ms | 3240.800 / 3955.313 ms | 970.890 ms |
| Long A2 | 5177.037 / 5412.884 ms | — | — | — |

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

## Artifact and review binding

- Formal private content-free report:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/pre-final-stable-agent-tts-20260825/formal-9600adbcf214a6bbc9dd6e08db4a8c59697854d3.json`.
- SHA-256:
  `712eab619ece2e59f14c7b87d154cb2f4b8e46a5b232c971c5606ede31c271e9`.
- File mode: `0600`.
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
