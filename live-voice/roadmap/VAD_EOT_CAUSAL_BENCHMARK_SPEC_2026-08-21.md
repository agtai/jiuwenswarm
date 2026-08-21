# VAD/EOT No-Browser Causal Benchmark Specification

> Date: 2026-08-21
>
> Review state: approved for implementation planning on 2026-08-21
>
> Exact design base: `465a21625bf253729f00b7c84e6cc08e9bd746a2`

## 1. Goal and decision boundary

Build a repeatable no-Browser benchmark that injects fixed 48 kHz PCM into the
real OpenAI streaming-recognition Adapter and determines whether a lower
server-VAD silence duration reduces final speech-to-EOT latency without
splitting a natural sentence-internal pause into multiple turns.

The first packet measures `1200`, `900` and `800` ms. It does not change the
product default. A lower value becomes eligible for a later source candidate
only after it passes the real-Provider corpus gate and is reproduced between
two stable `1200` ms controls.

If no lower fixed threshold passes, the correct result is to retain `1200` ms
and route a separate semantic/adaptive-VAD design. The benchmark must never
weaken its pause corpus to manufacture an improvement.

## 2. Why this is the next isolated experiment

Hongxing's 2026-08-20 physical analysis separated two independent waits. The
highest-priority P2 one-notification-per-RPC tail is now causally closed by the
accepted bounded-pull candidate. The next named wait is input finalization:
the formal normal-listening and barge-in paths both request Provider-native
server VAD with `silence_duration_ms=1200`.

D115 raised that value from 500 ms after a real sentence-internal breath pause
was cut into a separate turn. Therefore changing the constant without pause
quality evidence is not an optimization; it is a regression risk at the
authoritative committed-turn boundary.

This packet removes Chrome, microphone, Web UI, Agent, P2, TTS and playout from
the experiment while retaining the detector that actually owns product EOT:
the real streaming transcription Provider.

## 3. Selected approach and rejected alternatives

### 3.1 Selected: real Provider plus deterministic contract lane

The real lane directly instantiates `OpenAIStreamingSpeechProvider` with the
current `OpenAIStreamingSpeechConfig`, sends canonical
`RecognitionAudioFrame` values and consumes the real Provider's
`SPEECH_STARTED`, `SPEECH_STOPPED`, `COMMITTED` and transcription `FINAL`
events. It uses an explicit `RecognitionTurnDetection(SERVER_VAD,
ServerVadConfig(...))` for each threshold.

A deterministic fake-socket lane proves argument closure, frame pacing,
identity, event counting, report privacy, timeout, cleanup and forbidden-effect
oracles. It receives no latency or VAD-quality credit.

### 3.2 Rejected for the first packet: Gateway-only fake VAD

The Gateway owner can prove fencing and commit semantics, but a fake Provider
chooses when EOT occurs. It cannot determine whether an actual 1000 ms pause is
cut by the OpenAI detector.

### 3.3 Deferred: full Gateway/backend loopback

A complete service run adds media registration, WebSocket ACK, routing and
cleanup variance without improving the first threshold decision. It may be an
integration check after a lower threshold is eligible, but it is not required
for the screening benchmark.

## 4. Scope, exclusions and risk

- Capability/modules: Streaming Recognition, VAD/EOT and the Provider Adapter.
- Risk: Tier 2. EOT determines the boundary of the recognized and eventually
  committed user turn.
- Included: private corpus derivation, real-time PCM pacing, Provider session
  negotiation, EOT/final timing, transcript completeness, cleanup and a closed
  sanitized report.
- Excluded: changing the default threshold, semantic VAD, local VAD, Browser,
  microphone, Gateway media socket, Agent, Tool, Task, P2, TTS, history,
  playout, production configuration and remote refs.
- Product credit: none. The screening result may only select or reject a later
  default-change candidate.

## 5. Private corpus contract

The corpus root remains outside Git:

```text
/home/renan/openJiuwen-ai/live-voice-latency-corpus/vad-en-v1/
```

It is derived from one immutable 48 kHz mono PCM WAV in the existing `en-v1`
corpus. The builder performs no normalization, denoise, compression, speed or
pitch change. It inserts digital silence at one frozen low-energy boundary
between two spoken clauses.

Required cases:

| Case | Internal pause | Purpose |
|---|---:|---|
| `no-internal-pause` | 0 ms | control for ordinary final EOT |
| `internal-pause-300` | 300 ms | short hesitation |
| `internal-pause-600` | 600 ms | ordinary breath pause |
| `internal-pause-1000` | 1000 ms | D115-sensitive long natural pause |

Every file contains the same speech before and after the internal boundary and
at least 2000 ms of final digital silence. Every derived WAV is PCM signed
16-bit little-endian, 48 kHz, mono.

The private manifest is closed and contains:

- schema version and corpus ID;
- source relative path and SHA-256;
- frozen split frame and voiced-span boundaries;
- case ID, inserted pause, output relative path and SHA-256;
- sample rate, channel count and sample width;
- expected normalized transcript and required post-pause tokens;
- final silence duration.

Plain transcript text is allowed only in the private corpus manifest. Git
records hashes, case IDs and boolean completeness—not raw audio or transcript.

Transcript normalization is fixed: Unicode NFKC, `casefold`, replace every
non-letter/non-number code point with one space, collapse whitespace and trim.
The normalized final must equal the private normalized expectation exactly;
required post-pause tokens are an additional truncation oracle, not a looser
substitute for equality.

The builder refuses overwrite, path escape, noncanonical WAV, source-hash
mismatch, a split outside the declared low-energy boundary window, invalid
pause values or an output whose decoded facts differ from its manifest. The
split frame is explicit input and is never rediscovered during a benchmark run.

## 6. Real Provider data flow

For one attempt:

1. Read and verify the private manifest and WAV hash.
2. Resolve streaming Speech configuration from the existing environment names:
   `LIVE_VOICE_SPEECH_PROVIDER`, `LIVE_VOICE_SPEECH_API_BASE`,
   `LIVE_VOICE_SPEECH_API_KEY` and `LIVE_VOICE_SPEECH_STT_MODEL`.
3. Require the official OpenAI streaming route and create one fresh Provider
   instance and recognition identity.
4. Open a transcription session with exact server-VAD configuration:
   threshold `0.5`, prefix padding `300` ms, the experiment's silence duration,
   `create_response=false` and `interrupt_response=false`.
5. Require the Provider's effective-session echo to match those governed
   fields before sending audio.
6. Convert WAV PCM-s16le to float32 and send contiguous 20 ms, 960-sample
   `RecognitionAudioFrame` values under a monotonic real-time scheduler.
7. Drain Provider events concurrently so queue backpressure does not become
   the measured VAD delay.
8. Record the first monotonic observation of each typed speech/commit/final
   event. Never record partial or final text.
9. After Provider EOT, call `commit_recognition` only to observe
   `SERVER_VAD_PENDING` or `SERVER_VAD_OBSERVED`; no client commit may be sent.
10. Require one terminal final or one stable failed/unknown outcome, close the
    Provider and verify `cleanup_snapshot.clean`.

Frames are paced against an absolute monotonic schedule rather than chained
sleeps. Scheduler lateness is recorded. An attempt is invalid—not slow—when
absolute pacing drift exceeds 20 ms p95 or 50 ms maximum, because machine load
would otherwise be misreported as Provider VAD behavior.

## 7. Turn-integrity oracle

Each attempt must satisfy all of the following to be successful:

- exactly one `SPEECH_STARTED`;
- no `SPEECH_STOPPED`, `COMMITTED` or `FINAL` before the final post-pause voiced
  frame has been sent;
- exactly one `SPEECH_STOPPED`, one matching `COMMITTED` and one `FINAL`;
- every boundary belongs to the same exact Provider item and recognition ref;
- commit disposition is `SERVER_VAD_PENDING` or `SERVER_VAD_OBSERVED`;
- the deterministic wire lane proves no `input_audio_buffer.commit` is sent by
  the client; the real lane requires the corresponding server-VAD disposition;
- normalized final transcript matches the private expected transcript and
  includes all required post-pause tokens;
- the deterministic wire lane proves no audio frame is written after the
  Provider input fence; the real lane requires no accepted second turn or tail;
- Provider cleanup is complete and no task/socket remains retained.

An early EOT, two speech items, a missing tail clause, a mismatched Provider
item or an incomplete cleanup makes the attempt failed. It must never be
converted into an attractive latency number.

## 8. Timing metrics

All durations use one process-local monotonic clock:

- `session_open_ms`: open request to effective session ready;
- `final_voiced_frame_to_eot_ms`: scheduled send time of the final voiced frame
  to observed `SPEECH_STOPPED`;
- `eot_to_final_ms`: observed `SPEECH_STOPPED` to transcription `FINAL`;
- `final_voiced_frame_to_final_ms`: final voiced frame to `FINAL`;
- `provider_reported_speech_end_ms`: content-free Provider-time boundary;
- pacing lateness p50/p95/max.

Primary comparison metric: `final_voiced_frame_to_eot_ms` for successful
attempts. Turn integrity and transcript completeness are gates, not secondary
metrics that latency may trade away.

## 9. Screening sequence

The first execution is configuration screening, not a source candidate:

```text
A1: 1200 ms
E1:  900 ms
E2:  800 ms
A2: 1200 ms
```

The pilot runs one attempt per case in that order. If credentials, network,
Provider echo, pacing or cleanup fail, it stops without continuing to paid
repetitions.

After a clean pilot, each configuration runs five attempts per case. A1 and A2
must use the exact same clean source, environment labels, corpus hashes, model,
frame size, pacing policy and report schema.

A lower threshold is eligible only when:

- all 20 attempts succeed;
- every internal-pause case remains one turn;
- transcript completeness is 20/20;
- cleanup is 20/20 clean;
- no attempt is pacing-invalid or unknown;
- every case's `final_voiced_frame_to_eot_ms` p50 and nearest-rank p95 improve
  against the corresponding case in both A1 and A2;
- each case's A1/A2 p50 differs by at most 10% and neither control changes
  outcome counts.

If both lower values pass, prefer 900 ms unless 800 ms improves p50 by at least
another 80 ms without worsening any p95 or integrity result. This conservative
tie-break avoids buying marginal latency with less pause reserve.

## 10. Sanitized report contract

The report is one mode-600 JSON file outside Git. It is written once with
exclusive create and a closed schema containing:

- schema version, run ID, exact Git commit and clean-source fact;
- corpus ID and aggregate corpus-manifest SHA-256;
- Provider ID, implementation class and STT model label;
- threshold/configuration, case ID and attempt index;
- typed outcome and stable content-free reason;
- event counts, exact-identity booleans and transcript-complete boolean;
- timing metrics and pacing validity;
- cleanup-complete boolean;
- forbidden-effect counters;
- per-configuration summaries for attempts, success, failed, unknown, invalid,
  p50 and nearest-rank p95.

It must not contain API keys, authorization headers, API URL query values, raw
PCM, base64 audio, partial/final transcript, Provider item ID, exception text,
stack traces or private filesystem content beyond the declared corpus ID and
case IDs.

## 11. Forbidden effects

The runner imports no Agent/P2/Task/TTS owner and exposes counters fixed at
zero for:

- Agent submission;
- Tool execution;
- Task create/update/cancel/status mutation;
- P2 notification, PresentationUnit or ACK;
- TTS or audio downlink;
- history/store writes;
- Browser/media-device effects.

An unexpected call or import across one of these boundaries fails the attempt
and the complete run.

## 12. CLI and operational behavior

Planned entrypoints:

```bash
uv run python scripts/live_voice/prepare_vad_eot_corpus.py ...
uv run python scripts/live_voice/vad_eot_causal_benchmark.py pilot ...
uv run python scripts/live_voice/vad_eot_causal_benchmark.py run ...
```

CLI arguments are closed, canonical and bounded. The runner requires an
absolute private corpus manifest, absolute output path, exact Git commit and
unique run ID. It refuses dirty source, output overwrite, undeclared thresholds
or cases and missing/malformed Provider configuration.

Signals and cancellation settle the active Provider and produce no success
report. Provider/network faults use stable reasons and never reveal the private
exception. The runner performs no retry inside one attempt; repeated attempts
are explicit experiment units.

## 13. Implementation ownership

Planned files:

- add `scripts/live_voice/vad_eot_benchmark_support.py`;
- add `scripts/live_voice/prepare_vad_eot_corpus.py`;
- add `scripts/live_voice/vad_eot_causal_benchmark.py`;
- add `tests/unit_tests/live_voice/test_vad_eot_causal_benchmark.py`;
- add `tests/unit_tests/live_voice/test_prepare_vad_eot_corpus.py`;
- update this spec only for accepted clarifications;
- add a separate implementation plan after spec approval.

The first packet must not modify `streaming_speech.py`,
`openai_streaming_speech.py`, Gateway product code or the `1200` ms default.

## 14. Verification and review

Implementation follows TDD. Required evidence:

- RED/GREEN for corpus hashes/derivation and every CLI/report boundary;
- fake-socket session echo, ordered events, early-EOT, duplicate-EOT,
  transcript-incomplete, timeout, cancellation and cleanup tests;
- existing Streaming Speech, OpenAI Adapter and Gateway route regressions;
- Ruff, `py_compile` and `git diff --check`;
- one clean real-Provider pilot before the formal screening population;
- one independent Tier-2 module-boundary review before interpreting results.

Deterministic and fake evidence closes code behavior only. Real-Provider
attempts close the screening result. Neither grants Browser, microphone,
end-to-end or product-readiness credit.

## 15. Completion states

- `READY_FOR_SCREENING`: implementation/review pass and corpus/provider pilot
  are clean.
- `LOWER_THRESHOLD_ELIGIBLE`: one lower configuration passes every gate and
  beats both controls.
- `FIXED_THRESHOLD_REJECTED`: neither lower configuration preserves turn
  integrity; retain 1200 ms and route semantic/adaptive VAD design.
- `INCONCLUSIVE`: Provider/network/pacing/cleanup or A1/A2 stability prevents a
  truthful decision.

Only `LOWER_THRESHOLD_ELIGIBLE` authorizes planning a later product-default B
candidate. This spec itself authorizes no product change.

## 16. Related authority

- [current project status](../STATUS.md)
- [latency optimization plan](LATENCY_OPTIMIZATION_PLAN_2026-08-18.md)
- [D115 breath-pause VAD repair](../D115_S6_02_BREATH_PAUSE_VAD_REPAIR_2026-08-13.md)
- [testing authority](../../TESTING.md)
- [accepted P2 bounded-pull causal result](../evidence/P2_NOTIFICATION_BOUNDED_PULL_CAUSAL_RESULT_2026-08-21.md)
