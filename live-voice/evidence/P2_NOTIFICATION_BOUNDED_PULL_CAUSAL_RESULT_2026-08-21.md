# P2 Notification Bounded Pull — Causal A1/B/A2 Result

> Date: 2026-08-21
>
> Decision: **ACCEPT — P2 CAUSAL COMPONENT EVIDENCE ONLY**
>
> This record is exact-source evidence. It is not a Browser, Provider,
> first-audible, end-to-end, product-readiness or Production result.

## Question and rationale

Hongxing's physical investigation found a long post-model tail in which the Web
client consumed one retained P2 notification per request. At an approximately
85 ms request cycle, a backlog of 64 notifications can add more than five
seconds after model completion even though Agent generation has already ended.
The current branch retained that same structural behavior.

The experiment asked one narrow question: can a bounded pull remove this
transport serialization without changing notification order, final/error/Task
authority, replay identity, activation generation or any Agent, Tool, Task,
history or audio effect?

Bounded pull was selected ahead of alternatives because it is the smallest
change that attacks the measured cause:

- dropping or broadly coalescing deltas would change observation semantics and
  could hide an authoritative boundary;
- server push would add reconnect, backpressure and single-writer ownership to
  the first experiment;
- changing Agent/model execution would optimize a different stage;
- increasing concurrency with multiple outstanding polls would weaken the
  existing request sequence and replay fence.

The chosen limit is 16. It cuts the serial transport count substantially while
keeping Browser retention, parsing work and failure scope explicitly bounded.

## Implemented method

The implementation preserves the existing public Web API:
`nextNotification(): Promise<JsonObject>`. Batching is internal and default-off.

1. The Agent Conversation Runtime waits for no more than the first
   notification. It then drains only items already queued under the same exact
   notification-consumer lease.
2. The P2 adapter drains at most 16 items in publish order and stops after the
   first authoritative barrier.
3. The server returns `notification_batch` only when
   `JIUWENSWARM_LIVE_VOICE_P2_NOTIFICATION_BATCH_ENABLED=1` and the request
   carries canonical `max_notifications=2..16`. The legacy request and response
   shape remain unchanged while the flag is off or the client uses size 1.
4. Pure `chat.delta` or `chat.reasoning` observations may precede another item.
   Final, error—including nested `agent_event.error_reason`—Task/progress,
   source-event and PresentationUnit notifications are included as the last
   item and stop the batch.
5. One request ID owns one RPC-level `notification_sequence`. An identical
   retry replays the identical retained batch; a changed limit conflicts before
   dequeue.
6. The Web owner validates the complete batch before exposing its first item,
   enforces exact binding and increasing `publish_seq`, then serves the local
   bounded tail without another RPC. Close discards the tail and fences a late
   predecessor response.
7. The Panel uses one factory for initial, recovery and successor owners. The
   independent Web flag is
   `VITE_FEATURE_LIVE_VOICE_P2_NOTIFICATION_BATCH=true`.

The change does not alter notification production, Agent generation,
Presentation ACK, Tool/Task/history authority, STT, TTS, media or playout.

## TDD and review

RED was observed before each production boundary:

- missing runtime/adapter bounded drain;
- missing server flag, wire shape, barrier and replay behavior;
- missing Web batch parser/local queue and Panel flag propagation;
- repeated `publish_seq` across RPC batches;
- the candidate-neutral benchmark incorrectly tied operation sequence and its
  completion oracle to delivered item count;
- independent Tier-3 review reproduced a nested Agent error incorrectly
  allowed before a batch tail.

The final GREEN evidence included:

- 255/255 affected Python tests;
- 421/421 Integrated Web tests;
- production frontend build, 4,645 modules;
- Ruff, `py_compile`, scoped Prettier and `git diff --check`;
- independent Tier-3 result `READY`, with no remaining Critical, Important or
  Minor finding.

The applicable P/N/B/S/T/C/R/I/F/K/X dimensions cover positive ordered
delivery, malformed/bounded input, exact lifecycle and identity, delayed and
stale responses, single-flight polling, replay/conflict, independent
feature-off compatibility and the runtime→adapter→registry→Web→Panel seam.

## Experimental protocol

The causal runner uses the real compiled `ProductWebP2ActivationOwner` and a
deterministic fake transport. It publishes 10, 50 or 100 ordered notifications;
the last is `chat.final` with a PresentationUnit and every earlier item is a
pure delta. Each transport RPC waits 85 ms.

For every population:

- A1 runs five attempts on one clean reference commit;
- B runs five attempts on the named optimization commit;
- A2 repeats five attempts on the exact same A1 commit;
- batch input remains 16 in every run;
- the monotonic interval is model-complete to final-consumed;
- notification order, terminal shape and RPC count must be exact;
- submit, Presentation ACK, barge-in, P3, Agent, Tool, Task, history and audio
  effects must all remain zero.

Exact sources:

- harness/reference A1 and A2:
  `31f9209d66682d19745acd1d2c15a16b59fc75e2`;
- bounded-pull product B:
  `c1b4a47f51b0b200b12e2e544617577d7f307c69`.

Run IDs:

- A1: `p2-a1-r-batch16-20260821T001711Z-31f9209d6`;
- B: `p2-b-batch16-20260821T002105Z-c1b4a47f5`;
- A2: `p2-a2-r-batch16-20260821T002121Z-31f9209d6`.

Raw JSON reports are mode 600 and remain outside Git.

## Results

| Notifications | A1 RPC / p50 / p95 | B RPC / p50 / p95 | A2 RPC / p50 / p95 |
|---:|---:|---:|---:|
| 10 | 50 / 864.293 / 873.600 ms | 5 / 85.823 / 91.008 ms | 50 / 860.659 / 867.540 ms |
| 50 | 250 / 4,348.227 / 4,351.440 ms | 20 / 343.704 / 349.175 ms | 250 / 4,305.376 / 4,343.331 ms |
| 100 | 500 / 8,658.478 / 8,700.760 ms | 35 / 615.209 / 617.248 ms | 500 / 8,643.205 / 8,681.116 ms |

| Notifications | B p50 gain vs A1 / A2 | B p95 gain vs A1 / A2 |
|---:|---:|---:|
| 10 | 90.070% / 90.028% | 89.582% / 89.510% |
| 50 | 92.096% / 92.017% | 91.976% / 91.961% |
| 100 | 92.895% / 92.882% | 92.906% / 92.890% |

Every run completed 15/15 attempts and every forbidden-effect counter was
zero. A1 and A2 returned to the same 50/250/500 RPC curve, while B reached the
predeclared 5/20/35 totals. The improvement therefore follows the named P2
transport change rather than drift in the controlled delay or reference code.

## Interpretation and limits

The experiment supports retaining bounded pull and shows that the previous
one-notification-per-RPC tail was causal under controlled transport delay. It
does not prove that the complete product will improve by the same percentage:
real turns may have different notification distributions and overlap with
capture, STT, Agent, TTS, Browser scheduling and playout.

In particular, this experiment does not measure:

- microphone capture, VAD/EOT quality or STT finalization;
- real Agent/model/tool execution;
- TTS request or Provider first audio;
- WebSocket downlink, WebAudio scheduling or physical first audible;
- Presentation ACK, successor capture readiness or complete-round latency.

The next product-path gate is one clean physical Browser comparison on a source
that contains the accepted candidate. Further optimizations must use their own
unchanged A1/B/A2 owner-specific evidence rather than treating this P2 result as
a general latency baseline.

## Reproduction template

From the frontend directory of a clean worktree at the selected exact commit:

```bash
npm run benchmark:live-voice-p2-notifications -- \
  --output /absolute/private/run/report.json \
  --git-commit "$(git rev-parse HEAD)" \
  --run-id '<unique-run-id>' \
  --samples 5 \
  --delay-ms 85 \
  --batch-size 16
```

The runner rejects a dirty tree, a mismatched commit, invalid arguments and an
existing output file.

## Related authorities

- [bounded-pull implementation plan](../roadmap/P2_NOTIFICATION_BOUNDED_PULL_IMPLEMENTATION_PLAN_2026-08-21.md)
- [latency optimization plan](../roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md)
- [current project status](../STATUS.md)
- [testing authority](../../TESTING.md)
