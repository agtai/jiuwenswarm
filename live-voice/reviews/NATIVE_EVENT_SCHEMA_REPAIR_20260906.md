# Native transcript event compatibility repair

Baseline: `37994f0c1dcfb5ffb5556b354ccc5a6e10999f26`, clean and deployed.
The user requested diagnosis, repair and necessary local redeployment after the
new rehearsal failed with `ADAPTER_UPLINK_PEER_DETACH_MEDIA_CONSUMER_FAILED`.

## Evidence and intended behavior

The incident log records Agent completion at 15:37:10 and then
`NATIVE_PROVIDER_EVENT_NOT_CLOSED` at 15:37:10.663 in `_closed_event`. Closing the
Native session caused the next input frame to fail with `session_closed`; the
browser displayed that downstream transport failure as activation recovery.

A real `gpt-realtime-2` synthetic phrase probe reproduced the rejection: every
`response.output_audio_transcript.delta` included an extra string `obfuscation`.
The previous display repair added strict delta mapping using fixtures without
that Provider metadata. The real Agent and batch Speech checks did not exercise
this Realtime output schema, so they could not catch this regression. Private
field-name/type-only evidence is in `logs/native-event-schema-repair/`.

Accept and discard this optional string metadata only on the implicated delta
event. Preserve required fields, rejection of unknown fields/wrong types,
bounded transport decoding, Runtime admission, interruption and exact response
identity. Never use padding as transcript, audio, history or business authority.
Schema-rejection diagnostics should name the known event type and counts of
missing/unexpected fields without logging Provider field names or values.

Owner: Native Engine Provider mapper and its existing tests. Tier 2 compatibility
and failure-path repair; no shared product protocol, configuration, Task policy,
durability or model change. Reuse root TESTING.md's applicable matrix and the
current rehearsal packet. Exclude generic recovery redesign and performance work.

Acceptance: reproduce RED with realistic padded deltas; pass positive display and
interrupted/pre-admission cases, malformed/unknown/wrong-event rejection with zero
forbidden output, affected Engine/Session/Gateway checks, independent read-only
review, real Provider → Native Engine output through response completion, then
clean-source controlled deployment and unchanged Task/project state.

## Results

The bounded compatibility repair passed its module checks and independent
read-only review. The repair commit identifies the source; subsequent controlled
deployment identity is recorded in `logs/live_voice_runtime_contract.json` and
`logs/native-event-schema-repair/deployment-verification.json`.

- RED: four valid padded-delta cases failed with the incident reason; five
  malformed-event cases also exposed missing diagnostic event identity. Two
  unpadded cases already passed. Evidence: `red.txt`.
- GREEN: 244 tests passed across the Native Engine, shared Realtime Session and
  Gateway dedicated media test files. Evidence: `backend.txt`. No frontend
  behavior changed; prior browser evidence is not counted as a new full-suite run.
- Real Provider/Engine: a fixed synthetic utterance went through real TTS,
  `gpt-realtime-2` and the actual Native Engine. Three padded transcript deltas
  were accepted; four text updates and 100 audio frames were emitted, final
  transcript and `response.done` completed, and socket cleanup settled. No
  Agent/Task invocation or presentation/history ACK was issued. Evidence:
  `real-engine-output.json`; audio and transcript values were not retained.
- The first real Engine run also completed text/audio successfully but recorded
  the first bounded cleanup attempt as incomplete. The probe now drains the
  existing retryable close operation, and the repeated run confirmed completion;
  no production close behavior changed. Preserve `real-engine-output-first.json`.
- Independent reviewer checked the entire source/test diff, field scope, privacy,
  unchanged authority and negative output fences; no blocking finding. Main's
  cold diff and whitespace checks passed.
- Deployment baseline: 17 Task tables, 90 terminal Tasks, zero nonterminal Tasks
  and six project files, recorded read-only for comparison after restart.

| Applicable dimensions | Evidence |
|---|---|
| P / X | Real padded Provider deltas produce generated text and audio through response completion in the actual Engine. Runtime admission is a fixture in this probe, not a full Demo/Agent claim. |
| N / I | Unknown fields, missing response identity, null/object padding and padding on the wrong event reject before semantic mapping, with zero emitted actions/audio/delegates or additional Provider commands. |
| B / K | Absent, empty and nonempty string padding work; wrong types fail. Existing shared wire bounds and all affected Session/media checks pass. No other event gets relaxed field checks. |
| S / T / C | Admission before/after deltas and interrupt followed by late output remain fenced. This synchronous mapper change introduces no new await or concurrency owner. |
| R / F | Unknown future schema still fails closed with a content-free known-event diagnostic. Existing shutdown/recovery is retained; the real probe confirms cleanup settlement. |

Agent model selection is untouched. The user reported DeepSeek V4 Flash for the
incident; the Realtime parser failure is independent of which Agent generated
the answer, as the no-Agent Provider probe also reproduced it. Do not infer an
individual Agent call's model from the Native deployment model or startup warmup.

The launcher will reuse current configuration, project and data, with
`openai-realtime-native` / `gpt-realtime-2`, the existing headset profile and
NoBrowser. Required post-start checks are exact served bundle, four ports, Speech
readiness and unchanged Task/project hashes. Physical microphone/speaker and full
Demo business acceptance remain separate; no latency improvement is claimed.
