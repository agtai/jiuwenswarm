# Brainstorm — non-Agent P1/P2/P3 latency optimization

Date: 2026-08-21

## Purpose

Rank the remaining Live Voice latency opportunities owned by P1, P2 and P3
without changing Agent/model/tool execution. Estimates are planning ranges,
not additive promises or release targets. Each accepted change still requires
its own clean A1/B/A2 evidence.

“No Browser” in the immediate execution lane means no Chrome process,
microphone, speaker, WebAudio automation or device setup. Browser-owner
TypeScript may be exercised under Node with deterministic dependencies.

## Evidence reviewed

- Hongxing's private/public 2026-08-20 notes and physical logs;
- consolidated `WRAP_UP_HONGXING_LATENCY_FINDINGS_2026-08-21.md`;
- the article/PDF *从 30 秒到 2 秒：一套实时语音 Agent，是怎样不再“傻等”的*;
- historical A–G Browser-clock reconstruction in
  [LATENCY_EXPERIMENTS_2026-08-20.md](../evidence/LATENCY_EXPERIMENTS_2026-08-20.md);
- accepted [P2 bounded-pull result](../evidence/P2_NOTIFICATION_BOUNDED_PULL_CAUSAL_RESULT_2026-08-21.md);
- independently reviewed [VAD/EOT result](../evidence/VAD_EOT_CAUSAL_RESULT_2026-08-21.md);
- current source and Hongxing commits `6cd8840d5`, `874cf327c`, `35cae3d9a`
  and `e1df8b452`.

The PDF contributes architecture patterns—overlap, sentence boundaries,
bounded prefetch, single-writer delivery, generation fencing, backpressure and
fallback. It is not a JiuwenSwarm baseline.

## Corrected latency picture

Hongxing's physical turn reported:

| Stage | Observed time |
|---|---:|
| EOT → unified submit | 0.669 s |
| Agent admission | 0.680 s |
| model generation | 2.999 s |
| model complete → final presentation | 5.558 s |
| final presentation → TTS downlink | 1.683 s |

The 5.558-second post-model tail was P2 one-notification-per-RPC backlog, not
Agent execution. Bounded pull reduced the causal p50 by 90.0–92.9%. For the
observed approximately 64-notification tail, the structural projection changes
from about 5.44–5.56 seconds to about 0.34 seconds.

A post-P2 structural projection is therefore:

```text
speech stop → first scheduled audio
≈ VAD 1.2
+ EOT/submit 0.67
+ unchanged Agent admission/model 3.68
+ P2 bounded pull 0.34
+ presentation/TTS downlink 1.68
+ fixed WebAudio lead 1.0
≈ 8.6 seconds
```

This is not a new physical baseline. It exists only to bound headroom and avoid
ranking work from the obsolete 11.5-second projection.

## Work already completed

### P2 bounded notification pull

- Status: accepted causal component evidence.
- Measured gain: 90.0–92.9% p50.
- Example 100-notification p50: 8,658 ms → 615 ms.
- Remaining: physical product-path confirmation; optional push/coalescing is
  residual work, not the next primary lever.

### Fixed VAD threshold screen

- Status: 900 and 800 ms rejected; retain 1200 ms.
- Successful-turn p50 opportunity: roughly 285–412 ms.
- Failure: each lower candidate split all five exact 1000 ms pauses.
- Consequence: only semantic/adaptive or hybrid endpointing may recover that
  headroom without weakening turn integrity.

## Current branch divergence that changes priority

The current causal line contains the P2 bounded-pull candidate, but does not
contain Hongxing's later P1/P2 commits:

| Commit | Existing change | Expected role |
|---|---|---|
| `6cd8840d5` | rotate post-TTS capture leases after decaying local activity | recovery/long-listening correctness; little healthy-path p50 gain |
| `874cf327c` | open TTS downlink without waiting for successor-capture ACK | likely first-audio latency and reliability gain |
| `35cae3d9a` | separate completed playout receipt from early-duplex observation | prevents false post-playout failure/recovery |
| `e1df8b452` | restore hands-free playout controls | physical tested source containing the preceding fixes |

These commits must be compared and ported by current contracts, not blindly
cherry-picked across the divergent history.

## P1 input opportunities

| Candidate | Isolated p50 gain estimate | Confidence | Decision boundary |
|---|---:|---|---|
| early EOT/STT result waiter | 0–150 ms | medium-high | implement only if A1 proves ≥80 ms and ≥10% removable wait |
| semantic/adaptive VAD with 1200 ms fallback | 250–400 ms | medium | must preserve 1000 ms pause integrity |
| hybrid local + Provider VAD | 300–500 ms | medium-low | requires exact arbitration between two endpoint owners |
| STT session/pre-open tuning | 0–100 ms | low | streaming session already runs during capture |
| local faster-whisper primary | likely regression to at most 100 ms gain | low | batch CPU path loses current streaming advantage and quality |

The current Gateway event collector already waits for Provider final while the
uplink is active. The EOT join can overlap only result-request scheduling and
residual finish work with Browser drain/ACK/close. It is a useful A1 question,
not a presumed large optimization. Its governing spec is
[EOT_STT_SETTLEMENT_OVERLAP_SPEC_2026-08-21.md](EOT_STT_SETTLEMENT_OVERLAP_SPEC_2026-08-21.md).

## P1 output opportunities

| Candidate | Isolated p50 gain estimate | Confidence | Notes |
|---|---:|---|---|
| port successor-capture ACK decoupling | 300–1,000 ms | medium-high | Hongxing already implemented the owning contract on `874cf327c` |
| TTS connection prewarm/reuse | 200–600 ms | medium | current batch TTS generation observed at 912–1,672 ms |
| adaptive startup lead, 1,000 → 160–300 ms | 700–840 ms | high code fact | deterministic implementation possible without Chrome; physical underrun gate later |
| fixed authoritative phrase cache | 800–1,400 ms on hit | medium-high | only stable locale/provider/model/voice/version-bound ACK phrases |
| bounded next-sentence prefetch | 100–800 ms between sentences | medium | continuity gain, not necessarily first-audio gain |

The latency plan rejects the old suggestion of raising every queue to 64
frames. A first adaptive experiment should retain a bounded 12–16-frame window
only if inter-arrival/underrun evidence requires it. Large queues increase stale
audio and cancel backlog.

## P2 opportunities

| Candidate | Isolated p50 gain estimate | Confidence | Notes |
|---|---:|---|---|
| bounded pull 16 | already measured: 0.78–8.04 s | high | accepted |
| server push/single-writer after bounded pull | 200–500 ms only on high backlog | medium | reconnect, replay and backpressure cost |
| coalesce pure reasoning/delta | 100–400 ms on high backlog | medium-low | must not coalesce final, error, Task or Presentation barriers |
| batch size 16 → 32 | approximately 85–255 ms at 50–100 events | medium | larger retention/parsing scope for modest residual gain |
| ACK/next-turn processing overlap | 50–150 ms | medium | mostly next-capture readiness, not first audible |
| PresentationUnit handoff | less than 50 ms | high | observed 16–68 ms; not a primary bottleneck |
| Runtime-owned sentence → TTS overlap | 1.5–2.5 s ordinary; up to 3.5 s long response | medium | largest remaining structural candidate; high authority/cancel risk |

Sentence-level overlap does not modify Agent internals. Conversation Runtime
consumes deltas, admits only complete stable sentence boundaries, binds them to
the exact response/generation and starts bounded TTS before `chat.final`.
`chat.final` still owns complete text/history/terminal truth. Reasoning, Tool
fragments and provisional text never become speech.

## P3 opportunities without Agent optimization

| Candidate | Estimated gain | Kind | Authority requirement |
|---|---:|---|---|
| immediate Task accepted/queued acknowledgement | 2–7 s perceived | perceived | speak only a state already committed by Task Core |
| cached audio for fixed acknowledgement | 0.8–1.4 s on hit | perceived/TTS | exact text/locale/provider/model/voice/render key |
| short status/cancel PresentationUnit | 1–5 s perceived | perceived | no claim of running/completed before authoritative event |
| bounded Task/progress notification delivery | 100–500 ms in bursts | real | preserve Task order and terminal barrier |
| structured Task route avoiding unnecessary dialogue | 1–6 s where applicable | real | current bridge already partially provides this route; measure before changing |
| coalesce non-authoritative progress observations | 100–400 ms | real | never coalesce lifecycle/result truth |

Acknowledgement changes first perceived response, not final completion time. It
may say `accepted`, `queued`, `cancel requested` or `status retrieved`; it may
not promote those states to `running`, `applied` or `completed`.

## Three strategy portfolios

### 1. Conservative pipeline portfolio — recommended first

1. reconcile/port Hongxing TTS/capture commits;
2. establish a no-Chrome TTS first-audio causal benchmark;
3. port successor-capture ACK decoupling as one B candidate;
4. measure TTS prewarm/reuse;
5. run EOT waiter A1 and stop if below materiality;
6. evaluate semantic/adaptive VAD.

Expected cumulative non-Agent gain: approximately 1.0–2.0 seconds, with low to
medium authority risk. The estimates overlap and are not summed mechanically.

### 2. Streaming-output portfolio

- Runtime-owned stable-sentence TTS;
- bounded semantic prefetch;
- TTS streaming and cache;
- single-writer downlink;
- generation/cancel fences and bounded backpressure.

Expected additional first-audio gain: 1.5–3.0 seconds. Risk is medium-high
because old/provisional speech must remain zero.

### 3. P3 perceived-response portfolio

- authoritative short acknowledgement;
- fixed-phrase TTS cache;
- grouped progress observations.

Expected first perceived response: approximately 1–3 seconds. Final result
latency is unchanged.

## Cumulative projection

| State | Structural speech-stop → first-audio projection |
|---|---:|
| post-P2 current projection | ~8.6 s |
| TTS/capture decoupling + prewarm | ~7.3–8.0 s |
| semantic VAD + material EOT work | ~6.9–7.6 s |
| adaptive WebAudio lead | ~6.1–6.9 s |
| Runtime-owned sentence TTS | ~4.3–5.8 s |
| authoritative acknowledgement | perceived first response ~1–3 s |

Agent admission/model time remains in the projection but is unchanged. No row
is physical acceptance, and gains across rows overlap.

## Revised execution order

1. Compare `874cf327c` and `35cae3d9a` against current source and instantiate a
   current-contract port packet rather than reimplementing them.
2. Build the no-Chrome TTS first-audio benchmark with boundaries
   `PresentationUnit → request → Provider first chunk → downlink ready`.
3. Run A1 for the EOT waiter; implement only if it passes 80 ms/10%.
4. Evaluate TTS connection prewarm/reuse.
5. Specify P3 authoritative acknowledgement and bounded cache.
6. Evaluate semantic/adaptive VAD.
7. Specify Runtime-owned sentence-level TTS and bounded prefetch.
8. Defer WebAudio/device/physical confirmation until the Chrome lane is
   deliberately reopened.

Every candidate uses a separate clean worktree and:

```text
A1 clean reference
→ one named B change
→ A2 unchanged reference
→ stage/total/denominator/drift comparison
→ accept, revise or reject
```

## Limitations

- Estimates derive from source-bound physical evidence, historical Browser
  reconstruction and causal component runs; they are not all measured on one
  current source.
- P2, VAD, TTS and perceived-ACK gains cannot be added without accounting for
  overlap.
- Node/Python evidence can accept component behavior but not physical
  first-audible, microphone, speaker or WebAudio quality.
- No optimization here grants product-readiness or Production credit.
