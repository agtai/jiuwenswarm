# Stable-Sentence Agent-to-TTS Authority Specification

> **Status:** approved architecture, reviewed section-by-section with the user
> on 2026-08-21; causal screen and product candidate not implemented.
>
> **Planning branch:** `latency/stable-sentence-agent-tts`.
>
> **Planning base:** `4adc8ff0b74f4f2722733d55feba86b49c7c9ac8`.
>
> **Boundary:** Runtime-owned, default-off stable-sentence measurement and one
> conditional Agent-to-TTS overlap candidate. This specification grants no
> implementation, benchmark, real-Provider, physical Browser, first-audible,
> product-readiness, feature-complete or Production credit.

## 1. Objective

Measure and, only if material, remove the silent wait between the first
conservatively stable sentence in the real Agent output stream and the final
`chat.final` event.

The current formal route observes `chat.delta`, but
`AgentConversationRuntime._consume_agent_event` creates and dispatches a
`PresentationUnit` only for `chat.final`:

```text
Agent request
  -> chat.delta ... chat.delta
  -> silent wait
  -> chat.final
  -> PresentationUnit
  -> TTS request
  -> Provider first audio
  -> downlink first PCM
```

The proposed route allows the Conversation Runtime to turn a conservative
sentence candidate into an immutable presentation commitment while the Agent
continues generating:

```text
AgentEvent stream
  -> SentenceAccumulator
  -> StabilityPolicy
  -> StableSentenceCandidate
  -> Conversation Runtime presentation commitment
  -> bounded TTS/downlink
  -> Browser playout observation/ACK
  -> final reconciliation
```

This is not an Agent-Core or model optimization. It preserves the real Agent,
Tool and Task path and moves only the safe TTS handoff boundary.

## 2. Problem and current code facts

The latency inventory estimates ordinary structural headroom of 1.5-2.5
seconds, with up to 3.5 seconds for longer responses. Those values remain
`ESTIMATED` until the causal screen measures current-source event traces.

Current implementation facts are:

- `JiuWenSwarmAgentAdapter` maps each incremental `AgentResponseChunk` into a
  sequenced `AgentEvent`; a `chat.delta` payload is a fragment, not a formally
  cumulative immutable response;
- the Harness enforces event identity, source provenance, contiguous sequence
  and at most one usable `chat.final`, but does not assert that the final text
  preserves every prior delta byte;
- `chat.delta` is currently an observation-only notification;
- `chat.final` may normalize or rewrite streamed text and therefore remains the
  authoritative semantic-response boundary;
- the existing Presentation ledger already distinguishes `produced`,
  `enqueued`, `presented` and `invalidated` and forbids an already presented
  span from being silently rewritten;
- the formal TTS path already carries exact `ResponseRef`, unit identity,
  source span, content hash and Provider/downlink latency correlation;
- the existing presentation ACK proves a complete unit. It does not currently
  identify the exact word or audio frame heard inside an interrupted unit.

The problem is therefore not merely sentence splitting. It is deciding when a
mutable Agent prefix may become an irreversible audio presentation fact and
then reconciling that fact truthfully with final output, cancellation and
partial playout.

## 3. Scope, dependencies and exclusions

### 3.1 Capability and risk

- **Capabilities:** Conversation Runtime, Agent Bridge, Speech Synthesis,
  Realtime Media, Audio I/O, presentation/history truth and latency benchmark.
- **Risk:** Tier 3 for the product candidate because it changes audio and
  presentation authority across module boundaries. The causal runner is Tier 1
  validation tooling: its controlled mode is pure, while its provider-real mode
  may incur declared Provider calls but cannot enter product composition or
  mutate business state.
- **Dependencies:** D-043 response/generation and presented-ledger authority,
  D-044 Speech Synthesis identity/cancel boundaries, the existing formal P2
  notification route, the default-off latency probe, and the accepted P2/TTS
  checkpoint at the planning base.

### 3.2 Included

- generic accumulation of ordered Agent text fragments;
- a replaceable stability-policy interface;
- one conservative initial sentence policy;
- a no-product-effect causal materiality screen;
- one conditional product candidate after the screen gate;
- exact response/generation/unit/source-span identity;
- bounded TTS work and cancellation;
- final-prefix reconciliation, restart and correction semantics;
- A1/B/A2 comparison using the existing latency infrastructure;
- positive, negative, boundary, state, time/order, concurrency, recovery,
  identity, flag-off, compatibility and cross-module scenarios required by
  root `TESTING.md`.

### 3.3 Excluded

- Agent-Core/model selection, prompting or generation-speed changes;
- workload- or prompt-specific routing such as `dialogue_no_tool` branches;
- semantic/adaptive VAD or EOT/STT settlement work;
- multiple-sentence speculative prefetch beyond the single bounded window;
- fixed-phrase caching;
- WebAudio startup-lead optimization;
- Native speech-to-speech replacement;
- production authentication, multi-tenancy or public deployment;
- a claim of human first-audible latency without physical Browser evidence.

Tool, Task and ordinary dialogue traces exercise the same state machine. They
may contain different event barriers, but they must never select different
hard-coded product algorithms.

## 4. Authority model

Authority is deliberately split rather than assigned to one generic "final"
flag.

| Fact | Owner | Meaning |
|---|---|---|
| Raw Agent fragment and provenance | Agent Adapter/Bridge | Ordered observation; not yet semantic final or presented truth |
| Reconstructed response-local text | `SentenceAccumulator` | Deterministic concatenation of accepted text fragments |
| Sentence stability candidate | `StabilityPolicy` | Replaceable evidence that a bounded prefix is likely safe to speak |
| Presentation commitment | Conversation Runtime | Exact span is authorized for one response generation and may reach TTS |
| Synthesis/audio bytes | Speech Synthesis owner | Rendered output for one exact unit; no authority over response/history |
| Playout start/stop/complete | Browser Audio owner | Local physical playback observation |
| Complete presented unit | Presentation ledger after exact ACK | Immutable fact that the complete unit was presented |
| Semantic final text/history | `chat.final` plus Conversation Runtime/history policy | Authoritative assistant answer; never inferred from candidate or TTS |

A stable candidate is not a final Agent answer. Promotion means the
Conversation Runtime makes a bounded presentation commitment, not that it
declares Agent generation terminal or writes semantic history.

## 5. Data model

### 5.1 `SentenceStreamState`

One process-local state is retained per exact `ResponseRef`:

```text
response_ref
observed_text
observed_utf8_length
committed_utf8_end
last_agent_event_seq
next_candidate_seq
active_candidate_id | null
final_text | null
terminal_disposition
```

The state contains no credentials, user prompt, raw audio or cross-session
lookup. Text already exists in the Agent output owner and is retained only for
the active response lifetime and existing history/presentation work.

### 5.2 `StableSentenceCandidate`

The candidate is immutable and internal:

```text
response_ref
candidate_id
candidate_seq
source_start_utf8
source_end_utf8
content_ref
first_agent_event_seq
last_agent_event_seq
stability_policy_id
stability_evidence
```

It does not enter the shared wire protocol, Presentation ledger, chat history,
Task store or retained business result. Replacing or discarding it has zero
Agent, Tool, Task, audio, presentation or history effect unless it has already
been promoted.

### 5.3 Presentation promotion

Promotion reuses the existing `PresentationUnit` and `PresentationSurface.AUDIO`:

```text
StableSentenceCandidate
  -> PresentationUnit(
       ref=response_ref,
       surface=audio,
       unit_id=stable deterministic identity,
       seq=next contiguous audio sequence,
       source_start_utf8=candidate.start,
       source_end_utf8=candidate.end,
       content_ref=candidate.content_ref,
     )
```

Raw display text and its hash remain unchanged. Any spoken sanitization,
pronunciation or omission belongs in the existing auditable
`SpeechRenderPlan`; it cannot modify source-span authority.

No parallel sentence ledger, TTS identity or acknowledgement protocol may be
created.

## 6. Generic stability policy

The interface accepts only response-local accumulated text plus exact event
and generation facts. It returns zero or one new candidate. The first policy
is conservative and replaceable; future policies may consume an explicit
Adapter `speech_commit` capability or a Native model commitment without
changing downstream presentation authority.

The initial policy requires:

- exact current `ResponseRef` and contiguous Agent event sequence;
- a new non-empty UTF-8 source span after `committed_utf8_end`;
- a complete sentence boundary;
- visible non-whitespace lookahead after that boundary;
- no unclosed code fence or incomplete structured/code-like fragment;
- no forbidden control character or size-bound violation;
- no active cancel, replacement, Exit, terminal error or stale-generation
  fence;
- no crossing of a control barrier such as Tool transition or terminal event.

A control barrier closes the current mutable accumulation interval. It may
discard an unpromoted tail and prevent spans from crossing the barrier, but it
does not erase an ACKed prefix or manufacture a Tool/Task state. The rule is
event-based and applies identically across workload categories.

Punctuation alone is not authority. The policy produces a candidate; only the
Conversation Runtime may promote it.

## 7. State machine and bounded work

Candidate and existing presentation state compose as follows:

```text
Agent fragment
  -> OBSERVED
  -> STABLE_CANDIDATE
       | discard/replace
       v
     PROMOTED
       -> PresentationUnit.PRODUCED
       -> PresentationUnit.ENQUEUED
            | cancel/fence before complete ACK
            v
          INVALIDATED
            or
          PRESENTED
```

At most one early stable-sentence unit may be synthesizing, queued or playing
for a response. A second candidate remains mutable until the first unit is
presented or invalidated. This is an authority/backpressure bound, not a
prompt-specific rule. Multi-sentence prefetch is a separate later candidate.

Provider cancellation is necessary but insufficient. The Runtime and Browser
must fence late chunks by exact response generation and unit identity even when
the Provider continues returning an already-started synthesis request.

## 8. Final reconciliation and restart

`chat.final` is encoded as UTF-8 and compared against the exact concatenation
of promoted source spans. Fuzzy matching is forbidden. A documented existing
render-plan normalization may affect only speakable output, never this raw
source comparison.

### 8.1 Exact prefix match

- already presented spans remain immutable;
- promoted but unpresented matching spans retain their identity;
- only the final tail after `committed_utf8_end` receives a new unit;
- no previously committed sentence is replayed;
- semantic final/history uses the complete `chat.final` text.

### 8.2 Rewrite before promotion

The candidate and speculative work are discarded. Accumulation restarts from
the exact final or next valid event state. No presentation, audio, history,
Agent, Tool or Task effect is allowed.

### 8.3 Rewrite after promotion but before playout start

The exact unit is invalidated, TTS/downlink work is cancelled and all late
chunks are fenced. A replacement unit may be created from the authoritative
final without changing Agent/Tool/Task truth.

### 8.4 Rewrite after playout start

Audio that may already have been heard cannot be silently erased. The owner:

1. stops current playout and fences all future chunks;
2. records the old unit as `partial_playout_unknown` unless a complete unit ACK
   already exists;
3. preserves any completely ACKed prefix;
4. accepts a new corrective `ResponseRef` with a strictly newer response
   generation;
5. replays the authoritative final through the ordinary TTS path under that
   new generation;
6. keeps the correction relationship auditable and prevents the old response
   from writing new audio/history effects.

The corrective generation does not call Agent or Tool again and cannot mutate
Task state. It exists because restarting under the old identity would hide the
fact that the user may have heard a different prefix.

### 8.5 Duplicate and changed final

An exact duplicate final is idempotent. A changed final after reconciliation is
a protocol violation: it produces no additional unit, TTS, ACK, history or
business effect and leaves the exact response in a truthful failed/recovery
state.

## 9. Critical unresolved playout-cursor debt

> [!CAUTION]
> # TODO — EXACT WORD / AUDIO PLAYOUT CURSOR AUTHORITY
>
> The current ACK proves only one complete `PresentationUnit`. It cannot prove
> which words or audio frames were heard when a sentence is interrupted during
> playout.
>
> Until this TODO is closed:
>
> - partial playout is recorded as `UNKNOWN`;
> - no partial source span enters the presented ledger or semantic history;
> - a correction uses a new response generation;
> - duration estimates, `onstart`, queued audio and local silence cannot be
>   promoted to heard/presented truth.
>
> Closure requires one auditable authority:
>
> 1. word/phoneme timestamps from the TTS Provider mapped through the immutable
>    `SpeechRenderPlan`; or
> 2. a Browser audio-frame cursor plus a deterministic, audited audio-to-source
>    span mapping.
>
> Owners: Speech Synthesis, Audio I/O and Conversation Runtime. This TODO is
> mandatory before sentence-level overlap can be called Production-ready. It
> is deliberately not hidden by the first causal candidate.

## 10. Reuse of the existing latency probe

This work extends the existing probe. It must not create another run schema,
writer, privacy contract, cross-process clock join or A/B/A comparer.

Reused owners are:

- `jiuwenswarm.server.live_voice.latency_probe` for `LatencyProbeContext`,
  recorder/runtime/writer, redaction and `run.json` binding;
- `jiuwenswarm.server.live_voice.agent_latency_probe` for Agent-clock marks;
- `jiuwenswarm.gateway.live_voice.latency_probe` for Gateway/TTS shards;
- `jiuwenswarm.server.live_voice.latency_probe_report` for validation and
  p50/p95 reporting;
- `scripts/live_voice/post_capture_latency_runner.py` and the accepted
  checkpoint contract as patterns for isolated attempts, exact artifacts,
  fingerprints, drift and A1/B/A2 comparison.

Existing marks remain unchanged:

```text
agent.request_started
agent.agent_first_delta
agent.agent_final
agent.presentation_produced
agent.presentation_dispatched
gateway.tts_provider_transport_open
gateway.tts_provider_first_audio
gateway.downlink_ticket_ready
gateway.downlink_first_frame_sent
```

The first occurrence of each new sentence boundary adds:

```text
agent.sentence_candidate_detected
agent.sentence_presentation_committed
agent.sentence_candidate_discarded
agent.sentence_final_reconciled
agent.sentence_correction_started
```

Multiple candidates, discards and corrections are counters in the causal
report rather than repeated same-name probe marks.

No arithmetic subtracts clocks from different process domains. Gateway and
Agent shards remain drill-downs. The runner may report a total only when both
endpoints were observed on its own monotonic clock during the same attempt.

## 11. Causal screen

The screen is implemented before any product behavior change. It has two
layers and produces no product presentation, downlink, playout, history, Agent,
Tool or Task side effect. The provider-real layer may intentionally request and
discard benchmark-only TTS bytes; those calls and their cost are declared run
inputs, not product audio effects.

### 11.1 Controlled layer

A pure policy and causal runner consume deterministic sequenced Agent-event
traces under one controlled monotonic clock. TTS and playout are timing fakes.
This layer proves state transitions and measures controlled causal headroom; it
does not claim real model, Provider, Browser or audible latency.

Required trace classes include:

- append-only multi-sentence output with boundaries split across fragments;
- decimal, abbreviation, Unicode punctuation and closed/unclosed code fences;
- rewrite before candidate and before promotion;
- final mismatch before playout and after playout start;
- Tool/control barriers without workload-specific routing;
- duplicate, stale, reordered, gapped and wrong-generation events;
- barge-in, replacement, Exit, Provider failure and late chunks;
- exact final replay and changed-final rejection.

### 11.2 Provider-real layer

The provider-real screen uses the real current Agent path and configured TTS
Provider without Chrome. It records real Agent delta/final timing and real TTS
transport/first-audio/first-PCM timing. Environment, model, Provider, network,
source commit and configuration are fixed per population without recording
credentials or private content.

The Agent run disables side-effecting Tool/Task mutation. Any future real-Tool
screen must use a disposable isolated project/data directory and its own
explicit packet. Benchmark-only TTS output is retained only as bounded timing
and integrity facts and is never attached to a product media route.

This layer does not measure microphone capture, WebAudio scheduling, device
output or human first audible. Those remain explicitly `UNKNOWN`.

### 11.3 Truth classes

- `MEASURED`: two observed boundaries on the same monotonic clock;
- `CONTROLLED`: an injected deterministic delay or event fact, reported beside
  but never substituted for its observation;
- `DERIVED`: compatible same-population arithmetic such as B-A1, B-A2 and
  A1/A2 drift;
- `ESTIMATED`: prior headroom or a counterfactual prediction;
- `UNKNOWN`: Browser/device/human or missing-boundary truth not exercised.

## 12. Screen metrics and materiality gate

Same-clock Agent metrics are:

```text
agent.first_delta -> sentence.candidate_detected
sentence.candidate_detected -> agent.final
sentence.candidate_detected -> sentence.presentation_committed
agent.final -> agent.presentation_produced
```

Same-clock Gateway metrics retain current TTS boundaries. A runner-owned
controlled or provider-real attempt may additionally measure:

```text
response observed -> first PCM observed
candidate observed -> first PCM observed
final observed -> first PCM observed
```

Every report includes candidate count, promotion count, discard count,
prefetch/synthesis waste, prefix match/mismatch, corrections, duplicate/stale
rejections, terminal outcome and all forbidden-effect counters.

The product candidate is allowed only when the screen demonstrates all of:

- p50 `agent.final - sentence.candidate_detected >= 500 ms`;
- projected p50 first-PCM reduction of at least 400 ms and at least 10%;
- useful candidates in more than one trace class;
- zero final-prefix mismatch in the provider-real pilot before implementation;
- zero forbidden Agent, Tool, Task, product-audio/downlink/playout,
  presentation or history effect from the screen;
- no prompt/workload-specific product rule.

A failed gate produces a documented result and closes the lane without a
product candidate. It is not permission to lower the gate or silently switch
to another optimization.

## 13. One conditional product candidate and A1/B/A2

After a passing screen, B wires the same pure stability policy into the formal
Conversation Runtime and existing P2/TTS presentation route. No second
optimization is included.

```text
A1 = exact reference source with current chat.final TTS gate
B  = one stable-sentence presentation-overlap candidate
A2 = exact A1 source rerun after B
```

A1 and A2 use the same exact commit. B differs only by the declared product
wiring, flag and owner tests. Runner, policy, fixture bytes, timing profile,
Provider/model configuration and reporting code are identical across the three
populations. Reports show absolute stage/total p50/p95, B-A1/B-A2 milliseconds
and percentages, A1/A2 drift, failure rate, mismatch/correction rate and waste.

The candidate remains default-off until its complete acceptance closes.

## 14. Scenario and acceptance contract

The implementation plan must instantiate the complete applicable Tier-3
matrix from root `TESTING.md`; this specification does not replace that
authority.

### Positive

- an eligible sentence produces one exact AUDIO `PresentationUnit` and reaches
  TTS before `chat.final`;
- a compatible final emits only the unspoken tail;
- multiple sentences remain contiguous and never duplicate source spans;
- Tool and Task event streams traverse the same generic state machine and
  preserve their existing authoritative effects.

### Negative and boundary

- empty, oversized, invalid, gapped, ambiguous, code-incomplete, stale,
  wrong-scope and wrong-generation inputs fail closed;
- rewrite before commitment produces zero audio/presentation/history effect;
- duplicate or changed final produces zero duplicate unit or business effect;
- bounds cover response bytes, candidate bytes, active candidates and TTS work.

### State, time/order and concurrency

- cancel, replacement, barge-in, Exit and terminal error fence every future
  candidate/unit/chunk for the old response;
- delayed Provider output, reordered events and ACK races cannot revive an
  invalidated generation;
- candidate detection racing final reconciliation linearizes to one exact
  prefix/tail result;
- at most one early unit is outstanding and saturation cannot block critical
  cancellation.

### Retry and recovery

- replay of the same event/final/ACK is idempotent;
- retry cannot synthesize or present an already committed span twice;
- partial/unknown playout never becomes complete presented truth;
- restart with no durable cursor does not infer prior audible words.

### Identity, flag-off and compatibility

- session, scope, interaction, turn, response, generation, unit and source-span
  bindings are exact;
- feature-off preserves the current `chat.final`-only path and creates zero new
  timer, candidate, TTS call, writer or retained state;
- existing P2 bounded pull, successor-ACK decoupling, Agent/Tool/Task, history,
  presentation ACK and text-path tests remain compatible.

### Cross-module and real path

- controlled causal evidence proves code ordering only;
- provider-real no-Chrome evidence proves real Agent/TTS boundaries only;
- one later physical Browser journey is required before claiming first audible,
  partial-playout behavior or product-path acceptance;
- independent module-boundary review and cumulative seam review are mandatory
  before candidate acceptance.

Every failing or rejected path explicitly asserts zero forbidden Agent, Tool,
Task, audio, history, store and cross-scope mutation.

## 15. Completion and documentation boundary

The specification phase is complete when this document is reviewed and
committed. It does not activate implementation by itself.

The causal-screen phase is complete when its source, exact environment labels,
raw private artifacts and sanitized result are bound to one clean commit and
the materiality gate yields `PASS` or `STOP`.

The conditional product candidate is complete only after:

- A1/B/A2 passes with acceptable drift and absolute measured gain;
- every applicable Tier-3 scenario passes;
- independent owner and cumulative seam reviews close;
- feature-off and zero-forbidden-effect evidence pass;
- the result document separates measured, controlled, derived, estimated and
  unknown facts;
- STATUS is updated only with the exact evidence-backed capability consequence.

Even then, the exact word/audio cursor TODO and physical Browser first-audible
journey remain open before Production readiness.

## 16. Governing and supporting references

- root `TESTING.md` — risk, scenario and review authority;
- [current STATUS](../STATUS.md) — capability and product-truth authority;
- [D-043 and D-044](../decisions/DECISIONS.md) — response/generation,
  presentation ledger and Speech Synthesis authority;
- [latency optimization plan](LATENCY_OPTIMIZATION_PLAN_2026-08-18.md) —
  stable-sentence hypothesis and delivery order;
- [latency optimization inventory](LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md)
  — current source-bound headroom inventory;
- [accepted checkpoint specification](LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_SPEC_2026-08-21.md)
  — measurement truth taxonomy and A1/B/A2 precedent;
- `jiuwenswarm.server.live_voice.agent_conversation_runtime` — current Agent
  final/presentation owner;
- `jiuwenswarm.server.live_voice.presentation_ledger` — current presentation
  state and immutable-span owner;
- `jiuwenswarm.channels.web.frontend.src.features.live-voice.liveVoiceStreamingSpeech`
  — legacy/Demo conservative sentence/rewrite oracle only, not formal product
  authority.

The current product-truth repair packet in STATUS remains a separate execution
authority. This latency specification does not silently replace its priority or
grant capability completion credit.
