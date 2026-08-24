# Manual muted Live Voice latency pilot

> Date: 2026-08-24
>
> **Result: DIAGNOSTIC PARTIAL — NOT A BASELINE.** This record preserves
> source-bound partial timestamps from two manual attempts. It grants no
> fixed-corpus, p50/p95, audibility, Gate C, candidate or product-readiness
> credit. [STATUS](../STATUS.md) owns current judgement; the
> [experiment catalog](LATENCY_EXPERIMENT_CATALOG_2026-08-22.md) owns the
> compatible evidence route.

## 1. Question and boundary

The attempts asked whether a human speaker using Windows Chrome with WSL2
backends could collect the five-profile latency pilot after clearing the prior
chat context. The second attempt muted Windows output to remove acoustic TTS
feedback. Input remained real human microphone speech; no WAV/fake-device
injection or Browser automation was used.

Muted output preserves Browser scheduling and logical playout completion, but
cannot prove physical audibility, first heard word, echo cancellation or real
speaker quality. Cancelled batches retain their observed same-clock marks as
partial diagnostic timestamps; cancellation still forbids complete-round or
accepted-segment credit.

## 2. Provenance

| Field | Value |
|---|---|
| JiuwenSwarm commit | `37da36e68c84778db255d665c1c42e56da4147cf` |
| Source state | `docs_only_dirty`; no runtime/build input change |
| Browser/runtime class | Windows Chrome 151; WSL2 Python 3.11.15 backends |
| Speech | OpenAI `gpt-4o-mini-transcribe`; `gpt-4o-mini-tts` / `marin` |
| VAD / playout | Server VAD 1200 ms; WebAudio startup lead 1000 ms |
| Corpus | English manual v2; no-tool, Tool, background create/status/cancel |
| Driver | external manual driver SHA-256 `862c46832b6b5993015b37f48662a324a793ed7c300f2cc78269ebd9f54b776c` |

The first run ID, `lv-baseline-pilot-warm-en-v2-20260824T102905Z-37da36e68`,
produced three cancelled no-tool batches. The first recognition was inaccurate;
a successor capture then triggered an unintended barge-in during/after TTS,
and the operator advanced before the latest round settled. It was explicitly
invalidated and not extended.

The second run ID,
`lv-baseline-pilot-warm-muted-en-v3-20260824T104037Z-37da36e68`, produced six
Browser batches:

| Profile / round | Terminal | Use in this record |
|---|---|---|
| `dialogue_no_tool` / 0 | `completed` | Complete single-round diagnostic |
| `dialogue_with_tool` / 0 | `completed` | Complete single-round diagnostic |
| `task_create` / 0 | `cancelled` | Partial marks through first-start estimate |
| `task_create` / 1 | `cancelled` | No main waterfall pair completed |
| `task_status` / 0 | `cancelled` | Partial marks through first-start estimate |
| `task_status` / 1 | `cancelled` | Partial marks through first-start estimate |
| `task_cancel` | absent | The sixth beep belonged to `task_status` round 1 |

## 3. Stage-by-stage partial reconstruction

The ordinary reducer correctly reports cancelled segments as `unknown`. This
table separately subtracts only pairs of observed Browser marks inside the
same batch/clock. `0*` is a display sentinel meaning **not observed**. It is not
a measured zero and is excluded from every median, p50/p95 and future A/B/A.

| Segment (ms) | No Tool R0 | Tool R0 | Create R0 C | Create R1 C | Status R0 C | Status R1 C | Cancel |
|---|---:|---:|---:|---:|---:|---:|---:|
| EOT -> STT final | 644.0 | 565.1 | 587.6 | 0* | 489.3 | 733.6 | 0* |
| STT final -> submit | 1.7 | 0.2 | 0.2 | 0* | 0.2 | 0.2 | 0* |
| Submit -> presentation | 1,465.6 | 1,753.0 | 122,981.3 | 0* | 5,944.3 | 1,229.2 | 0* |
| Presentation -> TTS request | 0.7 | 0.3 | 0.3 | 0* | 0.1 | 0.3 | 0* |
| TTS request -> first downlink | 1,562.3 | 1,518.3 | 1,360.4 | 0* | 1,409.7 | 1,572.3 | 0* |
| First downlink -> schedule | 1.0 | 0.3 | 0.2 | 0* | 0.2 | 0.4 | 0* |
| Schedule -> first-start estimate | 728.0 | 722.5 | 716.7 | 0* | 731.1 | 744.9 | 0* |
| First-start estimate -> playout complete | 13,209.6 | 5,548.3 | 0* | 0* | 0* | 0* | 0* |
| Playout complete -> ACK | 19.2 | 15.5 | 0* | 0* | 0* | 0* | 0* |
| ACK -> next capture | 0.1 | 0.1 | 0* | 0* | 0* | 0* | 0* |
| Response total: EOT -> first-start estimate | 4,403.3 | 4,559.7 | 125,646.7 | 0* | 8,574.9 | 4,280.9 | 0* |
| Round total: EOT -> next capture | 17,632.2 | 10,123.6 | 0* | 0* | 0* | 0* | 0* |

## 4. Diagnostic headroom localization

Across the five batches containing both boundaries, and excluding every `0*`,
the cross-profile diagnostic medians are:

| Boundary | Observed range | Diagnostic median | Interpretation |
|---|---:|---:|---|
| EOT -> STT final | 489.3–733.6 ms | **587.6 ms** | Provider/VAD finalization candidate; not all removable |
| TTS request -> first downlink | 1,360.4–1,572.3 ms | **1,518.3 ms** | Largest consistent non-Agent residual in this pilot |
| Schedule -> first-start estimate | 716.7–744.9 ms | **728.0 ms** | Fixed 1000 ms WebAudio lead exposes stable logical wait |
| Submit -> presentation | 1,229.2–122,981.3 ms | **1,753.0 ms** | Workload/Agent/Task dependent; the 123 s create case is not a pure Live Voice residual |

The directly observed STT-final -> submit, presentation -> TTS-request and
first-downlink -> schedule seams remain approximately 0.1–1.7 ms. The three
consistent non-Agent bands above total about 2.83 seconds, but they are not
additive accepted headroom: endpointing, TTS transport/provider preparation
and Browser reserve have separate clocks/acceptance and may overlap with other
work.

For the two completed dialogue batches, Gateway drill-down located TTS request
to first Provider PCM at 1,216.9 / 1,151.8 ms. Provider-transport-open to first
PCM was only 13.1 / 12.3 ms, while first PCM to first downlink send was 323.0 /
326.7 ms. These are localization facts, not proof that TCP/TLS reuse or another
specific implementation removes those waits.

## 5. Workflow defects exposed

Muted output removed the initial speaker-feedback path for the two dialogue
rounds, but Task rounds still triggered barge-in/cancellation. The driver then
exposed three independent orchestration defects:

1. its beep reports any exported batch, including `cancelled`;
2. snapshots use the current stage rather than the batch's actual profile, so
   a `task_status` batch was saved under the cancel stage;
3. stored wrapper PIDs do not always retire spawned Vite/Gateway children.

Therefore `beep != completed`, and this driver version must not collect another
credited population without a terminal/profile-aware guard. The run remains a
useful diagnostic localization sample only.

## 6. Artifact binding and disposition

Raw paths and logs remain outside Git. The sanitized bindings are:

| Artifact | SHA-256 |
|---|---|
| v2 `run.json` | `33a9224a1d03125626e1ebc405e8b75e2a232d64028807258b1e38597ced8b0d` |
| v2 `browser.jsonl` | `849038e69e72ad65343c83a278b1fba233ef5c3334c93ecc4f881e36d6d761d3` |
| v2 `gateway.jsonl` | `b47994a3a1c820761e1973c86ff3ca5e1b5e77772a78415fafec1f7bfb150b75` |
| v3 `run.json` | `1b60495bd5ebea23c5128db412a74ba844ca820da923f228d02b52b1af252ede` |
| v3 `browser.jsonl` | `9239cc2b10ace56f7bf336992bec510038464bd132cea9b8029eab9717dafdfa` |
| v3 `gateway.jsonl` | `1fa6e9aa256013ccf30f7c70f32710e75e0b601b220414fa45f9d59aa009eaff` |
| v3 `report.json` | `65f1c98050a8ab13c2051856aa34b7aa6aa7dff76fa66708c14786c19dc73dc4` |
| v3 `report.csv` | `0d4848b96d4c1f2692e4a8d8d798beab958791af22d55f5b77fd7f2d791d5070` |
| v3 `report.md` | `67fa6fa6c78f15d4342750324146a2e5c4d1dd9e45fea511e5882a769fd21255` |

Decision: preserve the partial values for localization, retain all absent
boundaries as `unknown` in canonical reports, and keep fixed-corpus warm/cold
baseline credit open. A future retry uses a new run ID and unchanged corpus
only after the driver distinguishes terminal/profile/round and closes its
process tree.

## 7. Comparison with earlier evidence

The closest earlier Browser waterfall is the one completed
`dialogue_with_tool` round in `lv-manual-simple-to-paris-20260824-a` on
`497831f58`. The current Tool prompt, source, chat context and muted-output
condition differ, so the deltas are qualitative localization only, not A/B:

| Segment | Earlier round | Current Tool completed | Delta | Reading |
|---|---:|---:|---:|---|
| EOT -> STT final | 702.3 ms | 565.1 ms | -137.2 ms / -19.5% | Same broad Provider/VAD band; current sample faster |
| Submit -> presentation | 3,216.7 ms | 1,753.0 ms | -1,463.7 ms / -45.5% | Different Agent/Tool workload; not a Live Voice causal gain |
| TTS request -> first downlink | 1,561.1 ms | 1,518.3 ms | -42.8 ms / -2.7% | Essentially unchanged; stable material residual |
| Schedule -> first-start estimate | 579.0 ms | 722.5 ms | +143.5 ms / +24.8% | Fixed 1000 ms lead remains exposed; scheduling/buffer state differs |
| First-start estimate -> playout complete | 1,218.3 ms | 5,548.3 ms | +4,330.0 ms | Output duration/content difference, not pipeline regression |
| Playout complete -> ACK | 30.9 ms | 15.5 ms | -15.4 ms | Both immaterial single samples |
| Response total | 6,061.1 ms | 4,559.7 ms | -1,501.4 ms / -24.8% | Prompt/config incompatible; diagnostic only |
| Round total | 7,310.7 ms | 10,123.6 ms | +2,812.9 ms / +38.5% | Dominated by longer logical playout |

The earlier unmatched 250 ms playout-lead round recorded 46.7 ms
schedule→start, versus 722.5–728.0 ms for the current default-1000 dialogue
rounds. The approximately 681 ms difference reinforces LVL-09 materiality but
does not convert incompatible rounds into an accepted comparison.

The rejected connection-reuse experiment recorded 832.0 ms warm first PCM for
its own workload, while the current completed dialogues measured 1,151.8 /
1,216.9 ms. This difference is also non-causal. Current source locates almost
all of that interval before the `transport_open` mark, but that mark includes
more than a proven TCP/TLS handshake; the prior reuse implementation remains
rejected.

The older fixed-threshold VAD screen exposed 285–412 ms on successful turns but
failed pause integrity. The current 489–734 ms EOT→STT observations preserve
enough materiality for LVL-08 Semantic VAD while providing no reason to lower
the global 1200 ms fallback.

## 8. Next optimization-test sequence

1. **Harness Gate:** make beep/snapshot/advance terminal-, profile- and
   round-aware; reject extra/phantom batches; retire the complete child process
   tree. No new credited Browser population precedes this Gate.
2. **Dialogue baseline pilot:** use a new run ID and fresh chat, first collecting
   five no-tool and five Tool attempts under one fixed audio condition. Keep
   Task profiles in a separate lane so a 123 s Agent/Task path cannot invalidate
   P1/P2 measurement.
3. **LVL-09 A1/B/A2:** on the same source/prompt/device, compare
   A1=1000 ms, B=250 ms, A2=1000 ms. The muted screen may prove logical
   schedule/start and underrun/rebuffer; physical audible first-word credit
   requires a later headphones/unmuted Lane C.
4. **LVL-08 in parallel:** run the no-Browser Provider-native Semantic VAD
   `auto` and `high` A/B/A against the 1200 ms fallback with the natural-pause
   corpus and false-EOT gates.
5. **LVL-10 Provider screen:** after its prospective thresholds/group policy
   are frozen, run `LVL-10-A1/B/A2` current full-final SSE vs post-final bounded
   segmentation. First add/confirm substage attribution around the 1.15–1.22 s
   request→first-PCM wait; do not retry the rejected connection-reuse patch.
6. **P3 Task perception lane:** repeat create/status/cancel only after the
   harness Gate. If submit→authoritative accepted/queued presentation still
   waits near the observed 123 s Task-create path, specify a truthful early
   acknowledgement packet separately from Agent/Task completion.

The immediate order is therefore harness repair -> dialogue baseline ->
LVL-09, with LVL-08 runnable independently and LVL-10/P3 following their own
prospective Gates.
