# Realtime voice SOTA latency review

> Date: 2026-08-24
>
> This is a comparative technical review, not product acceptance, benchmark
> evidence or an architectural decision. Current product judgement and queue
> remain in [STATUS](../STATUS.md); measured experiment outcomes remain in the
> [latency catalog](../evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md); the
> [optimization inventory](../roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md)
> owns candidate status and headroom. External product internals are not
> inferred beyond their public documentation.

## 1. Confidence labels

| Label | Meaning in this review |
|---|---|
| `OFFICIAL` | Directly documented by the product or framework owner |
| `CODE FACT` | Directly observed in the current JiuwenSwarm source |
| `MEASURED DIAGNOSTIC` | Timestamp from one identified run, without population credit |
| `INFERRED` | Plausible architectural interpretation, not established by the cited source |
| `HYPOTHESIS` | Candidate mechanism or expected effect requiring a prospective screen |
| `UNKNOWN` | The available source does not establish the claim |

These labels are intentionally separate from the experiment catalog's truth
labels. In particular, a public API behaviour does not prove a provider's
internal model topology, and a single measured round does not define a stable
product percentage.

## 2. Publicly documented patterns

### 2.1 OpenAI Realtime

`OFFICIAL`: GPT-Realtime accepts and produces both text and audio over
WebRTC, WebSocket or SIP. The Realtime API supports server-side `semantic_vad`,
configurable eagerness and automatic response interruption when configured.
These behaviours allow endpointing, response generation and audio output to
remain inside one realtime session.

`INFERRED`, therefore not credited here: that the provider internally has no
STT, language-model or speech-synthesis sub-boundaries. The public surface is
realtime audio-in/audio-out; it does not disclose enough implementation detail
to prove the absence of internal stages.

JiuwenSwarm's planned LVL-08 uses the same public `semantic_vad` mechanism, but
not the same product authority policy. Its screen keeps automatic Provider
response creation/interruption disabled and retains the 1200 ms authoritative
fallback so that JiuwenSwarm, rather than the Provider, owns committed input
and Agent submission.

Sources:

- [GPT-Realtime model](https://developers.openai.com/api/docs/models/gpt-realtime)
- [OpenAI Realtime VAD](https://developers.openai.com/api/docs/guides/realtime-vad)

### 2.2 Gemini Live

`OFFICIAL`: Gemini Live uses a bidirectional streaming session, processes
realtime input incrementally, supports automatic activity detection with
start/end sensitivity and silence-duration controls, and can interrupt model
output. Current Live models can produce native audio output.

The session is persistent, but it is not immortal. The API exposes session
resumption and `GoAway`; resumability can also be unavailable during some
operations. The terms `eager` and `patient` are not the documented Google
configuration vocabulary, and `half-cascaded` is not established as an
internal architecture by these sources.

Sources:

- [Gemini Live API reference](https://ai.google.dev/api/live)
- [Gemini Live capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities)
- [Gemini Live session management](https://ai.google.dev/gemini-api/docs/live-api/session-management)

### 2.3 Claude Voice

`OFFICIAL`: Claude's user documentation describes spoken input, spoken output,
visible key points, natural pauses and user interruption.

`UNKNOWN`: whether the production implementation is a public STT -> LLM -> TTS
cascade, a native-audio model or another private composition. The public user
documentation does not establish that topology. Claude Voice therefore cannot
be used as technical evidence for sentence-level TTS or jitter-buffer design.

Source: [Claude Voice mode](https://support.claude.com/en/articles/11101966-use-voice-mode)

### 2.4 LiveKit Agents and Pipecat

`OFFICIAL`: LiveKit documents both realtime-model and STT-LLM-TTS pipelines.
Its TTS node consumes text segments; when a TTS implementation is not natively
streaming, the default path uses a sentence tokenizer for incremental
synthesis. Its turn owner combines detection and interruption semantics.

`OFFICIAL`: Pipecat separates raw VAD from conversational turn detection,
supports a local Smart Turn model and cancels in-flight bot work when an
interruption is accepted.

These frameworks support the general patterns of semantic turn detection,
incremental synthesis and bounded interruption. They do not establish a
universal rule that all open-source stacks use server push instead of polling.

Sources:

- [LiveKit pipeline nodes](https://docs.livekit.io/agents/logic/nodes/)
- [LiveKit turn handling](https://docs.livekit.io/agents/logic/turns/)
- [Pipecat speech input and turn detection](https://docs.pipecat.ai/pipecat/learn/speech-input)

## 3. Mapping to the current JiuwenSwarm waterfall

The following values are from exactly one completed
`dialogue_with_tool` round, `lv-manual-simple-to-paris-20260824-a`, on recorded
source `497831f58`. Its EOT-to-ACK total was 7310 ms. Other rounds in that run
failed or were cancelled. The values are useful for localization only; they
are not p50/p95, are not a stable percentage of product latency and cannot be
pooled with another workload or clock.

| Measured segment | One-round value | What the external pattern suggests | Current JiuwenSwarm interpretation |
|---|---:|---|---|
| EOT -> STT final | 702 ms | Semantic endpointing and continuous recognition | LVL-08 may reduce endpointing before EOT, but it does not automatically remove the entire 702 ms finalization segment |
| STT final -> submit | 0.9 ms | No material external technique needed | Already immaterial in this round |
| Submit -> presentation | 3217 ms | Native-audio systems can overlap model and audio output | This round includes Agent and Tool execution; it is not a pure Live Voice residual and native speech-to-speech would change the Registry/Task authority model |
| Presentation -> TTS request | 0.3 ms | Immediate authoritative handoff | Already immaterial in this round |
| TTS request -> first downlink frame | 1561 ms | Native streaming or segmented incremental TTS | Material diagnostic target, but current JiuwenSwarm already streams Provider audio deltas for the complete authoritative final |
| Downlink -> Browser schedule | 0.8 ms | Bounded transport and buffer ownership | Already immaterial in this round |
| Schedule -> estimated start | 579 ms | Smaller or adaptive startup reserve | A later 250 ms-lead round showed a 532.295 ms unmatched diagnostic delta; production remains at 1000 ms pending clean A1/B/A2 |
| Estimated start -> playout complete | 1218 ms | Primarily physical speech duration | Not removable pipeline wait; response length, speaking rate and codec can change it only with quality/semantic trade-offs |
| Playout -> ACK | 31 ms | Prompt receipt settlement | Small in this round; do not generalize without a population |

The original percentages such as 9.6%, 44%, 21% and 17% are deliberately not
retained as general shares. They are ratios inside one diagnostic round and
would change with prompt length, Tool use, Provider/network state, response
length and Browser scheduling.

## 4. Authority boundary and the post-final synthesis candidate

JiuwenSwarm must not speak provisional Agent deltas. Once audio is emitted it
cannot be retracted, while the Agent may revise a candidate before
`chat.final`. LVL-07 correctly screened the pre-final stable-sentence idea and
stopped for its tested workloads.

A distinct authority-compatible candidate exists:

1. wait for one complete authoritative `chat.final`;
2. derive bounded sentence or clause segments from that immutable text;
3. synthesize the first segment immediately;
4. prefetch a bounded number of later segments while preserving exact order;
5. fence and discard all not-yet-played segments on replacement, barge-in,
   cancellation or scope loss.

This is not a continuation or replacement of LVL-07. LVL-07 asked whether a
safe sentence existed *before* final. The new candidate starts *after* final
and asks whether segmentation beats the existing full-final streaming TTS.

Current source matters: `OpenAIStreamingSpeechProvider` already submits the
complete authoritative `spoken_text` to `/audio/speech` with SSE streaming,
publishes each `speech.audio.delta` as PCM frames and makes the first chunk
available before minting the media ticket. Segmentation therefore might reduce
Provider text preprocessing or improve inter-sentence continuity, but it can
also add request handshakes, rate-limit pressure and prosody discontinuities.
No 400–800 ms gain is accepted or estimated from current evidence.

## 5. Required materiality screen before product code

The candidate receives identifier `LVL-10` and remains `PLANNED`. Its first
screen requires no Browser because it changes the Provider synthesis boundary,
not capture or Browser scheduling. The declared comparison roles are:

| Role | Identifier | Route | Credit |
|---|---|---|---|
| Causal reference | `LVL-10-A1` / `LVL-10-A2` | Existing one-request, full-authoritative-`chat.final` SSE stream | Primary comparator |
| Candidate | `LVL-10-B` | Complete authoritative final split after `chat.final`; bounded ordered sentence/clause synthesis group | Candidate only |
| Optional diagnostic | `LVL-10-R0` | Batch/fallback route | Configuration/fallback diagnosis only; excluded from A1/B/A2 causality |

| Field | Required contract |
|---|---|
| A1/A2 | Existing one-request, full-authoritative-final SSE streaming path |
| B | Same final text split after `chat.final`, with bounded ordered synthesis |
| Dependencies | Same source, Agent final text, Provider, model, voice, format, region/network and warm/cold policy |
| Workloads | Short, medium and long final texts, including multi-sentence punctuation and an abbreviation/decimal integrity case |
| Primary timing | TTS request -> first Provider PCM and TTS request -> source playable reserve |
| Secondary timing | Complete audio ready, final playout duration projection, inter-segment gap, request count and Provider errors |
| Integrity | Exact final text coverage, exact segment order, no duplicate/omitted speech, bounded memory/requests |
| Negative gates | Injected replacement, group cancellation, Provider failure and malformed segmentation produce zero post-fence PCM, stale/unauthorized speech, Agent/Tool/Task/history mutation or false group completion/receipt |
| Stop rule | Do not build product wiring unless B materially improves the declared first-audio or continuity metric without integrity, reliability or cost regression |

The prospective spec must define source playable reserve as the Gateway-owner
time at which cumulative ordered PCM reaches one exact declared duration at one
declared sample rate. It must declare the reserve duration, sample accounting,
clock owner and `MEASURED`/`DERIVED` label before A1. That boundary is not
Browser first-audible credit.

The same spec must freeze the segmentation rule, maximum segment count,
maximum simultaneous Provider requests, prefetch depth, ordered-release rule
and intermediate-segment failure disposition. Physical microphone barge-in,
audible first-word integrity and real playout ACK remain outside phase 1.

Only after phase 1 passes its predeclared materiality/integrity gates may a
separate Browser Lane C measure first downlink, schedule/start, underrun,
rebuffer, audible first word, physical barge-in and receipt truth. It does not
retroactively redefine phase 1 as a Browser experiment.

Any future numeric gate belongs in that separate prospective spec before the
run. This review intentionally does not invent `>600 ms` or another threshold
from the one-round 1561 ms diagnostic segment. The 400–800 ms idea remains
uncredited.

## 6. Updated optimization route

1. Run LVL-08 Provider-native Semantic VAD with the 1200 ms fallback. Its
   250–400 ms range remains a hypothesis derived from successful fixed-VAD
   cases, not an accepted reduction of the 702 ms segment.
2. Run a clean same-source, same-workload playout-lead
   A1=1000/B=250/A2=1000. The current default stays at 1000 ms until physical
   completion, underrun/rebuffer and audible-output gates pass.
3. Specify and execute the no-Browser `LVL-10-A1/B/A2`
   authoritative-final segmented-TTS materiality screen, keeping optional
   Batch/fallback R0 outside causal credit. It is independent of the rejected
   LVL-07 pre-final overlap; Browser Lane C is conditional on Provider PASS.
4. Treat native speech-to-speech as a strategic architecture study only. It
   would require an explicit decision about committed conversation truth,
   Registry/composition, Tool/Task execution, cancellation and presentation
   authority before any product packet.
5. Keep batch-32, server push and notification coalescing frozen until a new
   deployed waterfall demonstrates material residual P2 backlog.

No item in this route receives accepted latency credit from this review.
