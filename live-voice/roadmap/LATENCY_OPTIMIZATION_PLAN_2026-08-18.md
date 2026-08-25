# Live Voice latency optimization plan

> **Plan status:** MINIMAL PROBE IMPLEMENTED — accepted current-source warm/cold
> measurement is not complete. [STATUS](../STATUS.md) remains the only owner
> of current priority, progress, blockers and completion credit. This document
> owns the latency diagnosis, implementation shape and acceptance boundary.
>
> **Code-fact analysis baseline:** frozen at
> `c8c2c2493987e808662ab0ad099d445ab918633a`;
> the latest product-code commit in that tree is
> `ca9a9d9a3be5f76c4feee980030a1b3ce065b9ab`. The two supplied analyses and the
> PDF *从 30 秒到 2 秒：一套实时语音 Agent，是怎样不再“傻等”的* are idea
> sources, not implementation or performance authorities. Read current Git and
> mutable product status from Git and [STATUS](../STATUS.md), not this frozen
> analysis baseline.
>
> Date: 2026-08-18

> **2026-08-20 measurement note:** the default-off minimal v0 implementation
> landed through `a1b0435dae6c19f9d4aaa58d5a96af2d2ce9af77`. Its contract and
> executable implementation packet are
> [LATENCY_PROBE_SPEC_2026-08-19.md](LATENCY_PROBE_SPEC_2026-08-19.md) and
> [LATENCY_PROBE_IMPLEMENTATION_PLAN_2026-08-19.md](LATENCY_PROBE_IMPLEMENTATION_PLAN_2026-08-19.md).
> Automated evidence does not establish physical latency. The real warm/cold
> baseline remains deliberately unclaimed until the runbook protocol is
> executed on clean source.

> **2026-08-21 targeted-measurement decision:** Hongxing's source-bound
> physical run at `e1df8b4529b073beed21affffda952bdb8262fc8` identified a
> separate P2 one-notification-per-RPC tail: approximately 64 notifications
> remained after model completion and consumed about 5.44 seconds at an
> approximately 85 ms Browser/RPC cycle. The immediate P2 optimization loop
> therefore uses a deterministic, no-Browser causal baseline before changing
> that transport. This is sufficient for a P2-specific A1/B/A2 decision, but
> it is not a physical Live Voice or end-to-end baseline and grants no capture,
> STT, TTS, WebAudio, playout or Production credit. A clean physical Browser
> validation remains mandatory before claiming a product-path improvement.

> **2026-08-21 P2 causal decision:** bounded pull was accepted at component
> scope after an exact A1/B/A2 run. The corrected harness/reference commit is
> `31f9209d66682d19745acd1d2c15a16b59fc75e2`; candidate B is
> `c1b4a47f51b0b200b12e2e544617577d7f307c69`. For 10/50/100 notifications,
> total RPCs changed from A1 50/250/500 to B 5/20/35 and returned to A2
> 50/250/500. B reduced p50 by 90.0–92.9% against both baselines with every
> forbidden Agent/Tool/Task/history/audio effect at zero. This accepts the P2
> transport candidate only; physical Browser validation and all other
> optimization layers below remain open.
> Full method, result and limitation evidence is recorded in the
> [P2 bounded-pull causal result](../evidence/P2_NOTIFICATION_BOUNDED_PULL_CAUSAL_RESULT_2026-08-21.md).

> **2026-08-24 route reconciliation:** Hongxing source `c31e85ade` repaired
> atomic P2 batch observation, passed scoped human validation with audible TTS
> and owns D-094 batch-16 default-on. LVL-07 then screened out pre-final
> stable-sentence overlap for its tested workloads. A 250 ms Browser startup
> lead produced only an unmatched diagnostic signal; the default remains 1000
> ms. The active latency route is now LVL-08 Provider-native Semantic VAD, a
> compatible LVL-09 playout-lead A1/B/A2, and prospective LVL-10 segmentation
> only after authoritative `chat.final`. The
> [experiment catalog](../evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md),
> [optimization inventory](LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md) and
> [SOTA review](../reviews/REALTIME_VOICE_SOTA_LATENCY_REVIEW_2026-08-24.md)
> own the current evidence interpretation. This dated note supersedes older
> queue language below where they conflict.

> **2026-08-25 execution update:** the immediate unverified working target is
> the externally reported approximately 5.6-second first-audio P95, reduced
> toward 3 seconds or decomposed honestly when the residual is outside
> JiuwenSwarm control. It is not repository evidence until a compatible
> source-bound run records it. Run
> LVL-09 WebAudio first as a physical pilot, then LVL-08 Semantic VAD; timed
> Provider populations remain sequential. In parallel, connect the missing
> Agent start/first-delta probe producers before attempting connection, warm-up
> or prompt-diet changes. The prior stable-sentence STOP remains valid only for
> its tested short/medium workloads. A separate long-form pre-final exact-prefix
> materiality screen may reopen that hypothesis, while LVL-10/LVL-10L remain
> stopped post-final chunking work.

> **2026-08-25 LVL-09 result:** same-workload schedule-to-start values were
> 718.549/48.432/721.306 ms for A1=1000/B=250/A2=1000, exposing approximately
> 670–673 ms of target headroom with 2.757 ms control drift. A1/B completed;
> A2 cancelled after the target mark. Treat this as target materiality, not a
> total-latency or physical/default acceptance result. Upstream Agent/TTS drift
> consumed the target gain in the single-run end-to-end totals.

> **2026-08-25 LVL-08/Agent result:** runner repair `5811aeb7f` and Semantic
> protocol/fault commits `3817aaaea`/`222582618` pass their scoped Tier-2/Tier-3
> reviews. A clean real AUTO retry completed the full 12-slot A1/B/A2 pilot.
> AUTO saved 684–734 ms of EOT on no-pause/300 ms cases but ended the 600/1000
> ms pause cases early, so it is integrity-rejected. HIGH was not run and 1200
> ms remains unchanged. Separately, Agent first-visible-delta commits
> `3b85425ac` and `4efd2b6c0` passed Tier-2 re-review but were still isolated
> and unmeasured at that checkpoint; the later result below supersedes that
> execution state.

> **2026-08-25 Agent first-delta result:** source `f71a5d830` completed a
> content-free real-Agent population, 15/15. Agent-start→first-delta p50 was
> 522.856/543.185/591.914 ms and first-delta→final p50 was
> 8.779/1676.287/3518.228 ms for short/medium/long output. Short remains
> non-material for pre-final segmentation; medium/long now justify a separate
> exact-prefix screen. This does not prove immutable-prefix authority and does
> not decompose queue, request preparation, connection/network or model
> first-token latency. See the
> [source-bound baseline](../evidence/AGENT_FIRST_DELTA_BASELINE_2026-08-25.md).

> **2026-08-25 LVL-12 result:** the conservative pre-final exact-prefix screen
> at `ea6475120` completed 10/10 real-Agent medium/long slots. Candidate→final
> p50 is 1587.308/3573.381 ms and Agent→candidate p50 is
> 657.947/707.935 ms. Both workloads pass the 500 ms materiality gate with zero
> forbidden effects. This authorizes only a separate no-Browser Agent→TTS
> component screen; it grants no `PresentationUnit`, speech, Browser or product
> authority. See the [LVL-12 result](../evidence/LVL12_PRE_FINAL_STABLE_SEGMENTATION_RESULT_2026-08-25.md).

> **2026-08-25 LVL-13 result:** source `9600adbcf` completed the separate
> no-Browser real-Agent/real-TTS A1/B/A2 population 30/30. Synthesizing the
> first retrospectively exact prefix reduced Agent→first-PCM p50 by
> 1723.166 ms / 52.510% medium and 3422.345 ms / 67.377% long versus
> interpolated controls, with valid control drift and zero forbidden effects.
> This accepts only the component candidate. Product presentation authority,
> Runtime/P2/Browser wiring and physical first-audible Gate C remain open. See
> the [LVL-13 result](../evidence/LVL13_PRE_FINAL_STABLE_AGENT_TTS_RESULT_2026-08-25.md).

## 1. Outcome and judgement

The useful target is not a headline “two seconds”. It is a conversation that
responds early without speaking provisional or stale content, while preserving
the existing response-generation, Task, history and cancel authorities.

Current code has a real streaming media path. The measured P2
one-notification-per-RPC backlog and successor ACK/receipt lifecycle have been
repaired at their accepted scopes, while LVL-06 found no material local EOT
settlement tail. Authoritative TTS still starts only after `chat.final`; Browser
playout retains a 1000 ms default lead, and the 1200 ms server-VAD fallback
protects natural pauses. The current plan therefore has four layers:

- retain compatible physical measurement as the product-path oracle;
- screen semantic endpointing without weakening commit authority;
- validate a smaller Browser reserve without promoting the unmatched sample;
- test post-final TTS segmentation without weakening Agent or speech authority.

Compatible measurement is a prerequisite, not observability polish. Without
it, a smaller queue or VAD value can make the median look faster while
increasing breath-pause truncation, audio underruns or stale speech.

## 2. Formal path under optimization and corrected baseline

The formal route being optimized is:

`AudioWorklet capture → dedicated media WebSocket → OpenAI streaming STT →
server VAD final → unified committed input → JiuwenSwarm Agent/Task route →
Conversation Runtime PresentationUnit → streaming TTS → dedicated downlink →
WebAudio playout`.

Important code facts are:

| Seam | Current fact | Latency consequence |
|---|---|---|
| Capture | `formal/audioPort.ts` produces 20 ms PCM frames. `browserAudioIOAdapter.ts` requests AEC/NS/AGC and uses the actual AudioContext sample rate; 48 kHz is not a product invariant. | Frame size is already suitable for streaming; codec replacement is not the first lever. |
| End of turn | `streaming_speech.py::ServerVadConfig` defaults to `silence_duration_ms=1_200`. [D115](../D115_S6_02_BREATH_PAUSE_VAD_REPAIR_2026-08-13.md) raised it from 500 ms after physical breath-pause failures. | A global return to 500 ms would trade latency for false commits. |
| Recognition final | `productP1VoiceRoute.ts::#stopAndRecognizeOnce` stops capture, drains and ACKs every frame, closes uplink, then calls `recognizeStreamingFinal`. | LVL-06 found at most 0.885 ms p50 removable local settlement tail; the remaining Provider-final wait is legitimate and no overlap change was authorized. |
| Submit | `components/ChatPanel/index.tsx` enables `handsFree: true`; `components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx` automatically submits the recognized final through the unified owner. The manual surface is hidden diagnostic compatibility. | The supplied analyses' “click Send” delay is stale for the formal product path. |
| Agent | `agent_conversation_runtime.py::_consume_agent_event` creates the text `PresentationUnit` only for `chat.final`; `chat.delta` is observation only. | The Agent's full 6–8 second historical generation time is silent before TTS starts. |
| Task commands | `voice_task_bridge.py::resolve_unified` already has a structured Task route and short authoritative speech for supported Task operations. | A new generic “fast Task route” is not the first task; its truth and latency should be measured and repaired where necessary. |
| TTS start | `productP1VoiceRoute.ts::playAgentText` sends the complete authoritative text. The Gateway pulls the first Provider audio before returning the downlink ticket. | Streaming exists below the full-text gate, so first audio still waits for `chat.final`. |
| Capture/playback overlap | The accepted first-audio path and later retained-receipt lifecycle no longer require successor readiness to own predecessor output. | Preserve the accepted decoupling; future receipt work needs new evidence rather than reopening this seam. |
| Browser playout | `browserAudioIOAdapter.ts` keeps `PLAYOUT_STARTUP_LEAD_DEFAULT_MS = 1000` and exposes a clamped 160–1000 ms diagnostic hook. | LVL-09 measured approximately 670–673 ms same-workload target headroom with near-zero control drift, but A2 cancelled after first-start; physical completion and a default change remain open. |
| Backpressure | the synthesis media queues default to eight frames, or 160 ms at 20 ms/frame. | Raising every queue to 64 frames would add up to 1.28 seconds of stale/cancel backlog and does not by itself solve Provider seed gaps. |

The only repository benchmark close to the whole route is
[D112 §8c](../D112_ALPHA_REAL_MEDIA_ROUTE_2026-08-13.md). Its five rounds used
a 4.54-second fixed utterance and reported Agent final at 6.04/7.70 seconds
(p50/p95), TTS first delivery at 1.20/1.96 seconds and whole-round completion at
17.16/17.71 seconds. It used the former 500 ms VAD and did not measure physical
browser first audible with today's one-second lead. A structural projection of
today's speech-end-to-first-audible path is roughly 11.5/14.5 seconds before
any unmeasured successor-capture delay, but this is an estimate, not a current
PASS or an SLO baseline.

## 3. Measurement contract

### 3.1 Preliminary-source boundary

The Hongxing materials reviewed before the current baseline are useful as
hypothesis sources, not as measurements for this branch:

- the PDF *从 30 秒到 2 秒：一套实时语音 Agent，是怎样不再“傻等”的* describes
  general pipeline overlap, bounded TTS prefetch, one WebSocket writer,
  generation fencing, backpressure and streaming-ASR fallback from another
  project narrative; it does not bind a JiuwenSwarm commit, current config or
  raw run population;
- the accompanying preliminary notes reuse five D112 rounds from an older VAD
  and playout boundary, then project later constants to estimate roughly
  11.5 seconds speech-end-to-first-audible; this is a diagnosis to test, not an
  observed current-source p50;
- those notes also describe a manual Send boundary that is stale for the
  current formal hands-free route, confirming why current code and current
  probes must outrank prose projections.

The working hypotheses remain sensible: waiting for full `chat.final`, the
fixed Browser startup lead, VAD tail and serial EOT settlement may dominate
more than STT final retrieval. The minimal probe must decide their actual
stage-by-stage and total contribution before any optimization or local-model
substitution receives credit.

### 3.2 Implemented minimal v0 boundary

The minimal implementation candidate writes one Browser additive timeline and
separate Gateway/Agent same-clock drill-down batches. The offline reducer joins
only compatible run/profile/case/round shards and rejects conflicting
correlation, interaction, activation, response or Task identity; it never
subtracts clocks across processes. Implemented boundaries include:

- Provider speech-stopped/EOT; browser EOT receipt; capture stopped; last frame
  sent and ACKed; uplink closed; STT final available; unified submit accepted;
- authoritative commit admission, semantic route resolution, Agent start,
  first delta, Tool execution, `chat.final`, Task command acceptance and
  presentation production/dispatch;
- TTS request, Provider first audio, downlink ticket, successor capture ready,
  browser first frame, WebAudio first frame scheduled and actually started;
- playout underrun/rebuffer and explicit streaming-STT fallback.

Sentence-level speakable output, prefetch waste, barge-in timing and a dynamic
cross-process critical path are outside minimal v0. They require a separately
declared experiment or later instrumentation packet rather than inference from
missing marks.

Raw audio, transcript content, credentials and private machine configuration
must not enter metrics. Existing `live_voice.segment_latency_ms` can carry
server segments, but current product composition and browser timings must be
wired rather than inferred from the schema's existence.

The development diagnostic baseline uses at least 20 successful rounds per
declared profile, records sample count/failure/fallback as well as p50/p95, and
separates cold and warm runs. Any critical scenario used for feature-complete
acceptance must be extended to the
[stable design](../architecture/FULL_SOLUTION_2026-07-30.md) §5.3 requirement
of at least 30 runs. The corpus must include short no-tool dialogue, tool
dialogue, supported Task create/status/cancel, Chinese breath pauses, barge-in
and one degraded network profile. It must measure both
speech-end-to-first-audible and complete round time; downlink-first-frame is not
a substitute for audible output.

This batch is done when the same response can be followed across all owners,
each missing segment is explicitly `unknown` rather than zero, and a fixed
current-source baseline can be reproduced without retaining private content.

### 3.3 Two measurement lanes after the P2 physical finding

The latency program now has two deliberately different lanes. They must not be
pooled or described with the same acceptance label.

The **P2 causal lane** requires no Browser, microphone, Speech Provider, TTS or
physical playout. A deterministic Agent fixture publishes a total of 10, 50 or
100 ordered notifications; the final element carries `chat.final` and every
earlier element is reasoning/delta. The real P2 owner/protocol consumes that
backlog under a controlled per-RPC delay and records, with a monotonic clock:

- model-complete to final-consumed latency;
- notification count, RPC count, batch size and remaining queue depth;
- dequeue, dispatch and final presentation boundaries;
- final/error/Task ordering, replay and terminal outcome;
- duplicate Agent, Tool, Task, history and audio effects, all asserted as zero
  where forbidden.

The first current-source run is P2 A1. One named optimization runs as B in a
separate worktree. Unchanged source then runs as A2. The environment, fixture,
controlled delay, populations and result schema must be identical; A1 and A2
must have the same commit, while B must have one different named source. This
lane can accept or reject the P2 transport change, but cannot establish
speech-end-to-first-audible, Browser playout or complete-round latency.

The **physical Browser lane** retains the existing fixed-corpus probe and real
Chrome validation. It is required after a P2 candidate succeeds causally and
before any claim that the product, Live Voice journey or perceived latency
improved. It also remains the only lane that can validate capture, VAD/STT
quality, WebAudio scheduling, real playout/ACK, barge-in audio fencing and
first-audible latency.

## 4. Remove avoidable waits on the existing authoritative path

### Remove the P2 one-notification-per-RPC tail first

Hongxing's 2026-08-20 physical run observed notification sequences 596 through
685. Model completion was near sequence 621; requests 622 through 685 consumed
about 5.38 seconds before the final presentation response, with an
approximately 85 ms median complete cycle. An earlier pre-auto-barge run showed
the same median and serial pattern. These values are evidence for Hongxing's
tested source, not a baseline for this branch, but the current source retains
the same structural one-request/one-notification owner and needs the causal A1
defined in §3.3.

The first implementation candidate, **bounded batch pull**, passed its causal
A1/B/A2 gate on 2026-08-21. One
request may return a closed, ordered batch up to an explicit limit. The client
processes the batch in order; final, error and Task notifications remain
reliable and may not be dropped, coalesced behind lower-value deltas or reordered
across presentation/ACK authority. Replay identity, activation generation,
bounded ledgers and one in-flight poll remain fail closed.

Server-side coalescing of non-critical reasoning/delta notifications remains a
possible later complement, but it changes observation semantics and must not
hide final/error/Task truth. Server push is deferred for the first candidate
because reconnect, replay, backpressure and single-writer ownership make it a
larger protocol change than bounded pull.

The P2 candidate receives causal credit only if it reduces final-consumption
latency and RPC count against both A1 and A2 without moving the wait, changing
the ordered terminal result, reviving a stale generation or adding duplicate
Agent, Tool, Task, history or audio effects. Physical Browser confirmation is
still required for product-path credit.

### Adaptive playout instead of a fixed one-second lead

The fixed lead should be replaced by an adaptive startup buffer driven by
observed Provider chunk inter-arrival and browser decode/scheduling health. A
reasonable first experiment is to start with 160–300 ms of contiguous decoded
audio, or a bounded timeout, then preserve a small reserve while playing.

The media frame window may grow modestly (for example to 12–16 frames) only if
the measurements show transport starvation. It must remain bounded and be
cleared synchronously by response-generation cancel. The PDF's useful idea is
bounded prefetch, not an unconditional large queue.

This change is accepted only if first-audible p50 improves, p95 underrun and
rebuffer do not regress, and barge-in leaves zero audible frames from the
cancelled generation after the defined stop bound.

### Do not gate first downlink on successor capture readiness

`#startConcurrentCapture` exists so the next user interruption can be heard,
but device/media activation should not sit serially between the first TTS chunk
and opening its downlink. The implementation should start capture preparation
and downlink establishment concurrently, keep capture ownership fail-closed,
and report if barge-in readiness arrives late. If capture preparation fails,
the product must surface degraded interruption capability; it must not discard
an otherwise authoritative response or claim hands-free readiness.

This seam is complete when first audio can flow independently, current
generation/cancel fences still own both streams, and tests cover capture-ready,
capture-late, capture-failed and cancel-during-startup cases.

### Overlap Provider final retrieval with local end-of-turn settlement

The Gateway already allows a server-VAD final to arrive before the browser
finishes its uplink. The product contract should expose “Provider final ready”
separately from “all local frames accounted for”, let the two settle in
parallel, and commit text only after both succeed. It must not simply call the
existing finish method early, because that would weaken complete-frame and ACK
proof.

Completion requires identical committed text and zero side effects on timeout,
missing ACK, stale capture or Provider-final failure, plus a measured reduction
in the EOT-to-STT-final segment.

### Tune VAD by evidence, not by a global constant change

Run a controlled 800/900/1200 ms comparison on the physical breath-pause
corpus. Semantic VAD may be evaluated behind explicit Provider capability and
configuration, but fixed and semantic modes must share the same commit/fence
contract. The default changes only if false-EOT, missed-EOT and latency evidence
all improve; 500 ms is not a candidate default unless new physical evidence
overturns D115.

Together these changes form the low-risk latency batch. Their expected gain is
roughly one to two seconds relative to the fresh baseline, but the measured
result, not this estimate, decides acceptance.

## 5. Speak useful truth before the full answer

### Authoritative acknowledgement for long operations

For tool or Task work that cannot produce a stable answer quickly,
Conversation Runtime may emit a separate short AUDIO `PresentationUnit` such
as an accepted/queued acknowledgement. It must be grounded in the state already
owned by Agent/Task authority: accepted or queued must never be announced as
running, applied or completed.

This is not a notification component calling TTS directly. Conversation
Runtime arbitrates the unit, assigns response generation and history policy,
and the ordinary TTS path renders it. Barge-in and replacement cancel it like
any other response. Fixed, non-private acknowledgement audio is a possible
bounded cache candidate after the ownership contract is proven; a cache key
must include normalized text hash, locale, Provider/model/voice, sample rate,
frame format and render/protocol version. Start in process, with an explicit
memory/retention limit; Redis is not a latency prerequisite.

This work is complete when the acknowledgement is truthful, heard within its
measured target, recorded or omitted from history according to one explicit
policy, and stale/wrong-scope/cancelled operations produce no audio or history
effects.

### Historical pre-final sentence-level Agent-to-TTS overlap — screened out

> **2026-08-24 disposition:** LVL-07 tested this materiality question with a
> real Agent and real Provider. Its projected gain was 177.2 ms p50 / 425.3 ms
> p95 and 7.43% relative p50, below all predeclared gates. The proposal below
> is retained as historical rationale but is not an active implementation
> packet. Reopening it requires a reviewed new workload or mechanism.

The original hypothesis was that releasing a stable first sentence before
`chat.final` could provide a large structural gain. Raw `chat.delta`
punctuation splitting in the browser is
not safe: a delta can be rewritten, a decimal or code block can contain
punctuation, and provisional audio cannot be retracted after it is heard.

The sentence owner belongs in Conversation Runtime. It should:

- accept only append-only Agent text under the current response generation;
- identify conservative speakable boundaries and assign monotonic unit/sequence
  identity plus exact UTF-8 source spans;
- emit each stable sentence as an authoritative AUDIO presentation candidate,
  while text history remains governed by the final authoritative response;
- reconcile `chat.final` with emitted spans, fail closed on a changed prefix,
  and never replay an already presented sentence;
- cancel the playing unit and all future synthesis/prefetch work on barge-in,
  replacement, stale generation, scope change or terminal error.

`liveVoiceStreamingSpeech.ts` and
`liveVoiceStreamingSpeech.test.mjs` provide useful conservative sentence,
rewrite and stale-epoch oracles, but they are currently wired only to the
legacy/Demo flag `FEATURE_LIVE_VOICE_STREAMING_SPEECH`. The formal path may
reuse the algorithm and tests; it must not route formal authority through that
hook or count the flag as product capability.

At the TTS layer use a bounded semantic prefetch window: while sentence N is
playing, N+1 may synthesize and at most one additional stable sentence may be
prepared. This is separate from the 20 ms media-frame queue. Metrics must show
prefetch hit/waste and inter-sentence audible gaps, and cancel must discard all
future units before they reach the media socket.

This batch is accepted only when sentence one can be heard before
`chat.final`, final text/history remain authoritative, and positive, rewrite,
duplicate-final, failure, barge-in, stale/wrong-scope and zero-forbidden-effect
tests pass on the formal Integrated Web route.

### Authoritative-final segmented TTS — LVL-10 materiality first

The authority-compatible follow-up begins only after complete `chat.final`.
It derives bounded sentence/clause segments from that immutable text, starts
the first segment and may prefetch a bounded number of successors while
preserving exact order and cancellation fences. It does not speak provisional
Agent deltas and is therefore distinct from the stopped LVL-07 proposal.

Current TTS already sends the complete final text to a Provider SSE stream and
publishes each `speech.audio.delta` as it arrives. Segmentation receives no
assumed 400–800 ms gain. Before product code, a no-Browser real-Provider
`LVL-10-A1/B/A2` must compare the existing full-final SSE stream with bounded
post-final segments under the same text/model/voice/network/warmth. Optional
`LVL-10-R0` Batch/fallback is configuration diagnosis only and receives no
causal credit.

The prospective spec must define source playable reserve as the Gateway-owner
time at which cumulative ordered PCM reaches one exact declared duration and
sample rate; declare its clock and measurement label; and freeze segmentation,
maximum segments/concurrent requests, prefetch, ordered release, intermediate
failure, numeric materiality, drift, reliability and cost rules before A1.
Phase 1 measures first PCM, source reserve, completion, inter-segment gaps,
requests, order, injected cancellation and zero forbidden effects. Physical
barge-in, audible first word and real playout ACK belong only to a conditional
Browser Lane C after Provider PASS.

## 6. Agent-path work after pipeline evidence

Current dialogue requests allow tools even for simple questions. After the
timeline shows where first stable text is delayed, a separate Agent batch may
add a clearly bounded no-tool route, prune unnecessary context/tool schemas,
ask for a short spoken conclusion before detailed screen text, and benchmark
faster model configurations. These are product/model choices and can change
answer quality or capability; they are not hidden defaults and are not part of
the first pipeline batch.

The Task structured route should be optimized only where measurement finds a
real delay. It must continue to obtain lifecycle/result truth from Task Core
and Executor rather than asking dialogue to infer it from conversation or
project files.

## 7. Delivery order and acceptance

Current latency work should be packetized in this dependency order:

1. preserve the accepted D-094 P2 default and retained ACK/receipt lifecycle;
   the missing fixed-corpus off/on population is an evidence gap, not an open
   repair;
2. preserve the LVL-09 target materiality result of approximately 670–673 ms.
   A2 cancelled after first-start, so keep 1000 ms as default until completed
   physical playout and reliability evidence close the Browser Gate;
3. preserve the LVL-08 protocol repair but reject AUTO after its 600/1000 ms
   continuation failures; retain 1200 ms and do not run HIGH;
4. preserve the 15/15 real-Agent first-delta baseline, then decompose queue,
   request preparation, connection/network and model first-token latency before
   specifying connection, warm-up or prompt-size candidates;
5. preserve the LVL-12 medium/long exact-prefix materiality PASS, LVL-13
   no-Browser real-Agent/real-TTS component acceptance and short STOP. Before
   product wiring, define and review immutable presentation authority,
   reconciliation and cancellation; then run deployed physical Gate C. Keep
   post-final LVL-10/LVL-10L independent;
6. consider authoritative acknowledgements for genuinely long Task operations
   only when perceived latency is the product priority;
7. treat native speech-to-speech as a separate strategic architecture study,
   not a latency packet under the current Registry/Task authority model.

This is an order of proof, not a request for one large patch. Each packet names
its P1/P2 owner, D-046 risk tier, flags/configuration, rollback path, positive
journey and applicable D-032/D-074 negative/review evidence from
[root TESTING](../../TESTING.md).

Initial targets are deliberately relative to the fresh baseline:

- the P2 candidate reduces final-consumption latency and RPC count against both
  causal baselines while preserving exact notification order, replay and zero
  forbidden effects; its numeric threshold is frozen only after A1 records the
  current-source 10/50/100 curves;
- the low-risk pipeline batch reduces speech-end-to-first-audible p50 by at
  least 1.0 second, with no p95 false-EOT, underrun, fallback or cancel
  regression;
- LVL-10 receives no threshold from this historical plan; its prospective spec
  must freeze first-PCM/source-reserve, continuity, drift, reliability and cost
  gates plus bounded group policy before A1;
- truthful acknowledgement, where applicable, has a working perceived-response
  target of 3–4 seconds;
- Task create/status/cancel receive a 3–5 second working target only after the
  current structured route has a physical baseline.

Targets become release gates only after environment, corpus and sample size are
frozen. No “2 second” claim is accepted without current physical p50/p95,
failure rate and quality evidence. Tests must also prove zero Agent, Tool, Task,
history and stale-audio side effects for partial ASR, stale/wrong generation,
wrong scope, synthesis failure and cancel races.

The 5–7 second and related bands above are intermediate optimization targets,
not replacements for the accepted stable-design latency table. Changing a
feature-complete release threshold requires reconciled current evidence and an
accepted product decision rather than a plan-only edit.

## 8. Explicit exclusions and reference judgement

This plan does not replace the current product-truth defect packet, complete
P3, Provider generalization or Production operations. It does not authorize a
Provider/model/billing change, persistent speech cache, new retention policy or
raw-audio storage.

Ideas retained from the supplied analyses/PDF are streaming overlap, bounded
sentence prefetch, ordered single-owner output, generation fencing, short
truthful acknowledgement and complete latency instrumentation. Ideas rejected
or deferred are direct browser TTS from raw deltas, multiple producers writing
one media socket, Redis before a bounded local cache is justified, a blanket
64-frame transport queue, Opus as the primary latency lever, a global 500 ms
VAD, and the article title as an SLO. Current code already supplies streaming
STT/TTS, bounded ordered media and generation fences; they receive no new
completion credit from appearing in the references.

The [2026-08-24 SOTA review](../reviews/REALTIME_VOICE_SOTA_LATENCY_REVIEW_2026-08-24.md)
adds official-source confidence labels to that comparison. It does not prove
external providers' internal model topology, turn one diagnostic round into a
population or authorize native speech-to-speech under JiuwenSwarm's current
Registry/Tool/Task/presentation authority.

## 9. Code and test anchors

The implementation packets should begin from these current owners rather than
from the reference materials:

- capture, EOT, recognition and playout orchestration:
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`;
- browser scheduling and capture constraints:
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts`;
- hands-free product integration:
  `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx` and
  `LiveVoiceIntegratedRoutePanel.tsx` in the same directory;
- VAD/provider configuration: `jiuwenswarm/server/live_voice/streaming_speech.py`
  and `openai_streaming_speech.py`;
- Agent presentation authority:
  `jiuwenswarm/server/live_voice/agent_conversation_runtime.py`;
- unified Task/dialogue routing:
  `jiuwenswarm/server/live_voice/product_composition_registry.py` and
  `voice_task_bridge.py`;
- TTS first-chunk and bounded downlink queue:
  `jiuwenswarm/gateway/live_voice/product_streaming_synthesis.py` and
  `streaming_synthesis_route.py`;
- current focused oracles:
  `tests/unit_tests/gateway/test_streaming_speech_route.py`,
  `tests/unit_tests/live_voice/test_agent_conversation_runtime.py`, and the
  frontend `productP1VoiceRoute`, `liveVoiceBrowserAudioIOAdapter` and
  `liveVoiceStreamingSpeech` `.test.mjs` files.

## 10. Status relationship

This plan is queued under the `Observability, benchmark and latency` capability
and dependency route to feature complete in [STATUS](../STATUS.md). The
2026-08-23 lifecycle repair packet is closed. Hongxing source `c31e85ade` owns
atomic P2 batch observation, D-094 default-on and its scoped human acceptance;
the initial authorization failure is closed for that declared run, while a
compatible fixed-corpus off/on population remains unclaimed. The `e1df8b452`
physical run supplies a scoped diagnosis of the P2 one-notification-per-RPC
tail; it is not the fresh fixed-corpus baseline required by this plan. The
[latency experiment catalog](../evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md)
owns the dated causal/deployed evidence. LVL-08, compatible LVL-09 and
prospective LVL-10 are the current latency sequence; none receives product
credit from this plan. Compatible instrumentation may be included in an
affected packet only when its ownership and acceptance are explicit; this
preparatory plan never outranks or activates the current STATUS route by
itself.
