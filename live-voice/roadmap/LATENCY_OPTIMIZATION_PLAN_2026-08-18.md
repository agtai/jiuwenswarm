# Live Voice latency optimization plan

> **Plan status:** P2 AND VAD CAUSAL SCREENS COMPLETE — accepted current-source
> physical warm/cold measurement is not complete. [STATUS](../STATUS.md)
> remains the only owner
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

> **2026-08-21 VAD/EOT causal decision:** a no-Browser real-OpenAI screening on
> `e2773bec2740e933721d1f598e06978b5b476860` ran exact total pauses of
> 0/300/600/1000 ms in A1/1200 → E1/900 → E2/800 → A2/1200 order. Both controls
> preserved 20/20 turns; 900 and 800 ms each preserved only 15/20. The fixed
> lower thresholds are therefore rejected and the 1200 ms product default is
> retained. This is Speech-Provider component evidence, not Browser or E2E
> credit. See the [VAD/EOT causal result](../evidence/VAD_EOT_CAUSAL_RESULT_2026-08-21.md).

> **2026-08-21 non-Agent priority reconciliation:** current source already
> collects Provider final concurrently with uplink media, so EOT result-waiter
> overlap is a conditional 0–150 ms hypothesis, not the next presumed large
> gain. The current causal line also lacks Hongxing's later TTS/capture commits
> `874cf327c` and `35cae3d9a`. The next no-Chrome packet therefore compares and
> ports those current-contract changes and establishes TTS first-audio causal
> boundaries. EOT A1 proceeds only behind its 80 ms/10% materiality gate. Full
> ranking and estimates are in the
> [non-Agent P1/P2/P3 brainstorm](NON_AGENT_P1_P2_P3_LATENCY_OPTIMIZATION_BRAINSTORM_2026-08-21.md).

## 1. Outcome and judgement

The useful target is not a headline “two seconds”. It is a conversation that
responds early without speaking provisional or stale content, while preserving
the existing response-generation, Task, history and cancel authorities.

Current code has a real streaming media path, but it still serializes several
waits on the first-audible critical path. Newer source-bound physical evidence
shows that, in the analyzed turn, the largest measured tail was the P2
one-notification-per-RPC backlog after model completion. Authoritative TTS also
starts only after `chat.final`; there is a fixed one-second browser playout
lead, a 1.2-second server-VAD silence threshold, serial end-of-turn cleanup, and
a successor-capture readiness wait before the TTS downlink is opened. The plan
therefore has four layers:

- establish a current-source causal P2 baseline without making an E2E claim;
- retain clean physical measurement as the product-path oracle;
- remove avoidable pipeline waits without changing product truth;
- overlap Agent generation and TTS at authoritative sentence boundaries.

The first layer is a prerequisite, not observability polish. Without it, a
smaller queue or VAD value can make the median look faster while increasing
breath-pause truncation, audio underruns or stale speech.

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
| Recognition final | `productP1VoiceRoute.ts::#stopAndRecognizeOnce` starts its result RPC after local drain/ACK/close, but Gateway's Provider event collector already runs concurrently with media. | Only result-request scheduling and residual finish work remain candidate overlap; A1 must prove ≥80 ms/10% before protocol change. |
| Submit | `components/ChatPanel/index.tsx` enables `handsFree: true`; `components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx` automatically submits the recognized final through the unified owner. The manual surface is hidden diagnostic compatibility. | The supplied analyses' “click Send” delay is stale for the formal product path. |
| Agent | `agent_conversation_runtime.py::_consume_agent_event` creates the text `PresentationUnit` only for `chat.final`; `chat.delta` is observation only. | The Agent's full 6–8 second historical generation time is silent before TTS starts. |
| Task commands | `voice_task_bridge.py::resolve_unified` already has a structured Task route and short authoritative speech for supported Task operations. | A new generic “fast Task route” is not the first task; its truth and latency should be measured and repaired where necessary. |
| TTS start | `productP1VoiceRoute.ts::playAgentText` sends the complete authoritative text. The Gateway pulls the first Provider audio before returning the downlink ticket. | Streaming exists below the full-text gate, so first audio still waits for `chat.final`. |
| Capture/playback overlap | Current causal source waits on successor-capture readiness before downlink. Hongxing's divergent `874cf327c` decouples that ACK but is not present here. | Reconcile/port the accepted contract and measure `PresentationUnit → Provider first chunk → downlink ready` before inventing another fix. |
| Browser playout | `browserAudioIOAdapter.ts::PLAYOUT_STARTUP_LEAD_SECONDS` is fixed at `1.0`; its test schedules the first two 20 ms sources at 11.00 and 11.02 when current time is 10. | This deliberately adds one second to first audible to mask Provider burst gaps. |
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

The controlled no-Browser 800/900/1200 ms Provider comparison is complete:
both lower fixed thresholds failed turn integrity on the exact 1000 ms case,
while both 1200 ms controls passed. Semantic VAD may now be evaluated behind
explicit Provider capability and
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

### Formal sentence-level Agent-to-TTS overlap

The largest structural gain comes from releasing a stable first sentence
before `chat.final`. Raw `chat.delta` punctuation splitting in the browser is
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

Work should be packetized in this dependency order:

1. ~~current-source no-Browser P2 A1 with the deterministic 10/50/100
   backlog;~~ **DONE — causal component evidence only**
2. ~~one named bounded P2 transport candidate B, followed by unchanged-source
   A2 and an A1/B/A2 accept/revise/discard decision;~~ **ACCEPTED — causal
   component evidence only**
3. ~~no-Browser real-Provider fixed-threshold VAD screen;~~ **DONE — 800/900
   rejected, retain 1200; component evidence only**
4. reconcile Hongxing's divergent TTS/successor-capture and playout-receipt
   commits against current source, then establish a no-Chrome TTS first-audio
   A1 before porting one candidate;
5. run the no-Chrome EOT waiter A1 and change protocol only if its 80 ms/10%
   materiality gate passes;
6. evaluate TTS connection prewarm/reuse and semantic/adaptive VAD as separate
   owner-scoped A1/B/A2 packets;
7. authoritative acknowledgement for genuinely long operations;
8. Conversation Runtime-owned sentence streaming with bounded semantic
   prefetch;
9. clean physical Browser confirmation of accepted causal candidates, without
   retroactively relabelling component evidence as E2E;
10. Agent/model/tool-path changes only where the preceding evidence still shows
   material delay.

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
- the sentence-streaming batch reduces p50 speech-end-to-first-audible by at
  least 40%, with a working target band of 5–7 seconds for ordinary dialogue;
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
and dependency route to feature complete in [STATUS](../STATUS.md). The current
execution packet remains the higher-priority authoritative product-truth defect
repair. Latency implementation starts as its own P1/P2 quality packet when the
dependency route has a clean candidate and has migrated the applicable test
oracles; compatible instrumentation may be included earlier in an affected
defect packet only when its ownership and acceptance are explicit.

The P2 causal lane does not require a rebase onto Hongxing's divergent
`hx/0819_live_voice_p1p2` line. Run it first on the reviewed current source and,
when useful, independently on Hongxing's tested source. Before physical product
credit, compare Hongxing's three functional P1/P2 fixes in a clean worktree and
integrate them as reviewed coherent packets if they are not already equivalent.
A blind rebase of the active dirty W3 worktree is not part of this route.
