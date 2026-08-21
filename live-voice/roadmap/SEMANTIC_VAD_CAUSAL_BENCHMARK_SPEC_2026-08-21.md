# Semantic VAD causal benchmark and candidate specification

Date: 2026-08-21

Status: approved design; implementation and real-Provider evidence pending

## 1. Decision and position in the latency route

The next VAD optimization is a Provider-native Semantic VAD screen, not another
global fixed-silence reduction and not a second semantic-model RPC. The current
`server_vad` configuration with `silence_duration_ms=1200` remains the product
default and the exact feature-off/configuration fallback.

This packet follows, and does not combine with, the existing
[EOT/STT settlement-overlap packet](EOT_STT_SETTLEMENT_OVERLAP_SPEC_2026-08-21.md):

1. run the EOT/STT materiality screen;
2. implement the early waiter/join candidate only if the existing 80 ms and 10%
   materiality gates both pass;
3. close that packet as accepted or rejected;
4. use its resulting clean source as the control source for this Semantic VAD
   packet.

The VAD comparison changes only turn detection. Any accepted EOT/STT overlap is
held constant across every A1, B and A2 arm.

This work remains P1/P2 Speech and Interaction Intelligence quality work. It
does not establish product readiness, feature completeness or Production
readiness.

## 2. Evidence that constrains the design

The credited fixed-threshold experiment in
[VAD/EOT causal result](../evidence/VAD_EOT_CAUSAL_RESULT_2026-08-21.md) showed:

- `server_vad=1200` preserved 20/20 complete turns;
- 900 ms and 800 ms each preserved only 15/20;
- every lower-threshold failure was an early EOT at the exact 1000 ms natural
  sentence-internal pause;
- successful lower-threshold cases exposed approximately 285--412 ms of
  latency opportunity, but that opportunity cannot be purchased by truncating
  a valid turn.

The current `gpt-4o-mini-transcribe` Realtime path cannot supply a local
pre-EOT semantic classifier: input transcription begins for a committed turn.
The Provider's transcription-session contract instead offers native
`semantic_vad`, which combines acoustic VAD with a semantic turn-end model and
supports `auto` and `high` eagerness. See the official OpenAI
[Realtime server-event API](https://platform.openai.com/docs/api-reference/realtime-server-events/input_audio_buffer/committed)
and [GPT Transcribe model contract](https://developers.openai.com/api/docs/models/gpt-transcribe).

Therefore the candidate uses the existing Provider connection and does not add
another model call, socket or billable semantic-decision RPC.

## 3. Objective and hypotheses

The packet answers two causal questions:

1. Can native Semantic VAD preserve complete natural-pause turns under the
   current authoritative commit/fence contract?
2. If it can, does either `eagerness=auto` or `eagerness=high` materially reduce
   the successful-turn latency from the final voiced frame to accepted STT
   final compared with `server_vad=1200`?

The primary hypothesis is that semantic endpointing can wait across a
sentence-internal pause yet stop earlier after a semantically complete
utterance. The null result is valid: if neither candidate preserves integrity
and improves latency, the product remains on 1200 ms with no Semantic VAD
activation surface.

## 4. Capability, ownership, risk and dependencies

- Capability: P1/P2 Streaming Speech turn detection and Interaction
  Intelligence endpointing.
- Implementation owners: typed Speech model, OpenAI Streaming Speech Adapter,
  Gateway Streaming Recognition owner, and a validation-only no-Browser
  runner.
- Risk: Tier 3 under root `TESTING.md`, because this adds a shared Provider
  protocol mode and changes the source of the authoritative EOT boundary.
- Dependencies: clean closure of the EOT/STT packet; exact current Provider and
  model configuration; valid credentials/network; private immutable corpus.
- Independent review: module-boundary review is required before credited real
  runs. Product promotion additionally requires the cumulative seam review and
  human product journey required by `TESTING.md`; the no-Browser screen does
  not claim that acceptance.

## 5. Typed contract

The experimental implementation adds the following closed concepts:

- `RecognitionTurnDetectionMode.SEMANTIC_VAD`;
- `SemanticVadEagerness.AUTO` and `SemanticVadEagerness.HIGH`;
- an immutable `SemanticVadConfig` whose response-creation and interruption
  authority are both fixed to `false`;
- explicit `RecognitionProviderSupport.semantic_vad` provenance;
- Semantic-VAD-specific Provider commit dispositions while retaining the
  existing Server-VAD dispositions unchanged for compatibility.

`RecognitionTurnDetection` must contain exactly the config matching its mode.
Manual mode carries neither VAD config. Server mode carries only
`ServerVadConfig`. Semantic mode carries only `SemanticVadConfig`.

The OpenAI Adapter sends a transcription-session `turn_detection` object with
the exact requested `type`, `eagerness`, `create_response=false` and
`interrupt_response=false`. It accepts an echo only when:

- the effective type and eagerness match the request;
- any echoed authority booleans are false;
- no unknown field changes the governed contract.

An absent capability, unsupported eagerness, malformed echo or incompatible
event sequence fails closed. It must not be relabelled as a successful Server
VAD run.

Internally, the Provider owns commit for both VAD modes. The implementation may
generalize its private commit owner, but it must preserve public Server-VAD
values and existing consumers. Semantic VAD must emit the same exact ordered
boundary family:

```text
SPEECH_STARTED -> SPEECH_STOPPED -> COMMITTED -> FINAL
```

Only committed final text can proceed beyond Speech. Partial text never gains
Agent, Tool, Task, history or response authority.

## 6. Activation and fallback boundary

The initial packet adds typed Adapter support and the validation runner only.
It does not add a product environment flag, Web setting, UI control or default
change.

The 1200 ms fallback is chosen before opening a recognition session:

- feature absent/off: use the current `server_vad=1200` route;
- Semantic VAD capability absent or candidate rejected: retain that same route;
- approved later activation: choose one exact mode before Provider open.

There is no silent same-turn retry. If an already-open Semantic VAD session
fails, it terminates with a typed failed, unknown or degraded outcome and
bounded cleanup. Replaying its audio into a new Server VAD session could
duplicate or truncate the user turn and is forbidden.

## 7. No-Browser causal runner

The runner exercises the real typed Streaming Speech and OpenAI Adapter seam.
It:

1. validates one immutable private manifest and every WAV hash before Provider
   allocation;
2. opens one recognition stream with the selected typed turn-detection config;
3. sends contiguous 20 ms, 48 kHz PCM frames against absolute monotonic
   deadlines;
4. observes Provider `SPEECH_STARTED`, `SPEECH_STOPPED`, `COMMITTED` and
   transcription `FINAL` events;
5. performs no client commit for either Provider-owned VAD mode;
6. closes the Provider and requires a clean cleanup snapshot;
7. writes one immutable, mode-600 sanitized report outside Git.

Browser, microphone, Gateway media WebSocket, Agent, Tool, Task, P2 semantic
routing, TTS and playout are outside this component experiment. Their absence
must be recorded rather than estimated.

Absolute pacing drift above 20 ms p95 or 50 ms maximum makes an attempt invalid,
not slow. Invalid attempts do not contribute latency samples.

## 8. Corpus strategy

### 8.1 Fast materiality and safety screen

The first screen reuses the credited private `vad-en-v1` corpus and its exact
four cases:

| Case | Internal pause | Purpose |
|---|---:|---|
| `no-internal-pause` | 0 ms | ordinary completed-turn control |
| `internal-pause-300` | 300 ms | short hesitation |
| `internal-pause-600` | 600 ms | ordinary breath pause |
| `internal-pause-1000` | 1000 ms | long natural pause that rejected 800/900 ms |

This phase permits fast comparison with the fixed-threshold evidence. It cannot
authorize a general product default because every case derives from one spoken
sentence.

### 8.2 Semantic generalization gate

A screen-passing candidate must then run against a new immutable private
English corpus containing, at minimum:

- a semantically complete declarative sentence;
- a direct question;
- a complete command;
- a hesitation/filler followed by continuation;
- a trailing conjunction or syntactically incomplete clause followed by
  continuation;
- a multi-clause utterance with a natural internal pause;
- a semantically complete short answer;
- equivalent final-silence controls.

The manifest owns exact expected normalized transcript, required post-pause
tokens, final voiced-frame location, pause samples, audio properties and file
hashes. It remains private because it contains human speech and transcript.

This first packet is English-only. A passing result remains explicitly
unproven for Chinese, Portuguese, other languages, different Providers/models,
far-field devices and uncontrolled noise. It cannot authorize a global default.

## 9. Turn-integrity oracle

An attempt succeeds only when all of these facts hold:

- exactly one matching `SPEECH_STARTED`;
- no `SPEECH_STOPPED`, `COMMITTED` or `FINAL` before the last required
  post-pause voiced frame is sent;
- exactly one matching `SPEECH_STOPPED`, `COMMITTED` and `FINAL`;
- every boundary belongs to the exact recognition ref and Provider item;
- the disposition proves the selected Provider VAD owns commit;
- no client `input_audio_buffer.commit` is sent;
- normalized final transcript equals the private expectation and contains all
  required post-pause tokens;
- no frame is accepted after the Provider input fence;
- no second turn or stale tail is accepted;
- pacing is valid and cleanup is complete;
- every forbidden-effect counter is zero.

Early EOT, missing tail text, multiple speech items, mismatched identity,
client commit, post-fence audio, timeout or incomplete cleanup fails the
attempt. Failed, unknown and invalid attempts never receive an attractive
latency value.

## 10. Timing metrics

All comparison durations use one process-local monotonic clock:

- `final_voiced_frame_to_eot_ms`: scheduled send of the final voiced frame to
  observed `SPEECH_STOPPED`;
- `eot_to_final_ms`: observed `SPEECH_STOPPED` to transcription `FINAL`;
- `final_voiced_frame_to_final_ms`: final voiced frame to transcription
  `FINAL`;
- Provider-reported speech-start/end values as content-free diagnostics;
- pacing lateness p50, p95 and maximum.

The primary endpointing metric is `final_voiced_frame_to_eot_ms`. The total
component metric is `final_voiced_frame_to_final_ms`. `eot_to_final_ms` detects
whether an apparently faster EOT merely moves waiting into STT finalization.

Reports show p50 and nearest-rank p95 per case and configuration. Integrity is
a gate, never a weighted quality score.

## 11. Experiment sequence

Each candidate has an independent A/B/A block:

```text
Block AUTO
  A1: server_vad, silence_duration_ms=1200
  B1: semantic_vad, eagerness=auto
  A2: server_vad, silence_duration_ms=1200

Block HIGH
  A1: server_vad, silence_duration_ms=1200
  B2: semantic_vad, eagerness=high
  A2: server_vad, silence_duration_ms=1200
```

First run one pilot attempt per case and arm. Stop on credentials, network,
protocol, pacing, identity or cleanup failure. After a clean pilot, run five
attempts per case and arm. Every arm in a block uses the exact source commit,
Provider/model labels, corpus hashes, frame size, pacing policy and report
schema.

The blocks are independent so one eagerness result cannot hide drift or
integrity failure in the other.

## 12. Eligibility and selection gates

For the four-case fast screen, a B arm is eligible only when:

- all 20 attempts succeed;
- every pause case remains exactly one complete turn;
- transcript completeness and cleanup are 20/20;
- no attempt is invalid or unknown;
- every case improves `final_voiced_frame_to_eot_ms` p50 and p95 against the
  corresponding case in both A1 and A2;
- no case regresses `eot_to_final_ms` or
  `final_voiced_frame_to_final_ms` enough to erase its endpointing gain;
- each A1/A2 p50 differs by at most 10% and the controls have identical outcome
  counts.

Passing this screen only admits the candidate to the semantic-generalization
gate. The expanded corpus requires 100% integrity, transcript completeness,
valid pacing and cleanup across all formal attempts, plus an improvement in
the completed-turn cases without a latency regression in continuation cases.

If both eagerness modes pass, prefer `auto` unless `high` improves the primary
p50 by at least another 80 ms in every completed-turn case without worsening
any p95, integrity or total-component result. This conservative tie-break
avoids trading natural-pause reserve for a marginal aggregate gain.

The possible decisions are closed:

- `SEMANTIC_VAD_AUTO_ELIGIBLE`;
- `SEMANTIC_VAD_HIGH_ELIGIBLE`;
- `SEMANTIC_VAD_NO_MATERIAL_GAIN`;
- `SEMANTIC_VAD_INTEGRITY_REJECTED`;
- `SEMANTIC_VAD_PROVIDER_INCOMPATIBLE`;
- `SEMANTIC_VAD_EVIDENCE_INCOMPLETE`.

## 13. Failure, cancellation and privacy

- Cancellation fences publication, cancels the exact owned Provider call and
  awaits bounded cleanup.
- Delayed, duplicate, reordered or wrong-identity events cannot revive a
  closed attempt.
- A timeout is not a negative latency value and does not become success.
- Provider/process-control exceptions retain their existing safe handling.
- Raw PCM, transcripts, Provider item IDs, credentials, URLs with query values,
  exception text and private filesystem paths must not enter reports or logs.
- Reports retain only content-free case/config labels, outcome enums, booleans,
  counts, timings, hashes and sanitized environment labels.
- The runner uses exclusive create, mode 600 and refuses to overwrite a prior
  run.

## 14. D-032 verification matrix

| Dimension | Required evidence |
|---|---|
| `P` | Server VAD control and both Semantic VAD modes produce one exact complete turn on eligible cases |
| `N` | Unsupported capability/eagerness, malformed echo, early EOT, missing tail and incomplete final fail closed |
| `B` | Closed enum/config fields, corpus/hash/audio bounds, report schema and Provider queue/time bounds |
| `S` | Open, fenced, committed, terminal and closed states cannot be duplicated or revived |
| `T` | Delayed, duplicate, reordered, pre-fence/post-fence and timeout events preserve exact order |
| `C` | Concurrent finish/cancel/event publication retains one Provider commit and one terminal result |
| `R` | Partial open/send/final failures clean up without replaying audio or manufacturing fallback success |
| `I` | Recognition ref, generation, Provider item and configuration arm remain exact and isolated |
| `F` | Feature-off/default remains `server_vad=1200`; unavailable Semantic VAD is truthful and bounded |
| `K` | Existing manual and Server VAD contracts, dispositions and tests remain compatible |
| `X` | Real current Provider proves wire echo, EOT/commit/final order, timing and cleanup; fakes receive no real-path credit |

Every path capable of touching audio or downstream authority asserts zero
forbidden Agent, Tool, Task, P2, TTS, history, Browser and other-scope effects.

## 15. Deliverables and completion boundary

Required deliverables are:

1. typed Semantic VAD model and Adapter contract, feature-off in product;
2. deterministic protocol, ordering, failure and compatibility tests;
3. extended no-Browser A/B/A runner and closed sanitized report schema;
4. immutable private English semantic corpus and verifier;
5. pilot plus formal real-Provider reports for `auto` and `high`;
6. independent Tier-3 module review and a sanitized result document bound to
   the exact clean tested commit;
7. an explicit eligible/rejected/incomplete decision.

Completion of this packet does not activate Semantic VAD in the Web product.
If one candidate is eligible, a later promotion packet must add the bounded
configuration surface, cumulative integration checks, rollback instructions
and human product acceptance. Until then, the product remains on
`server_vad=1200`.
