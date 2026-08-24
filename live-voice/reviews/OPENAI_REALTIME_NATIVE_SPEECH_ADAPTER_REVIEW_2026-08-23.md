# OpenAI Realtime native Speech Adapter review — 2026-08-23

## Disposition

**SECOND REPAIR SOURCE/AUTOMATION PASS — THIRD INDEPENDENT REVIEW REQUIRED.**

The original automated matrix passed, but a later independent review of exact
source `774f6ae7025990c7418a69e44b9f2cd38347ed4b` returned `C0/I3/M1`. It
demonstrated replayed audio release, illegal transcript/audio order acceptance,
no-progress events renewing the stream indefinitely, permissive native VAD
authority echoes, and effective translate/whisper model-purpose bypass. It
also identified missing production-factory and exact audio-boundary regression
oracles. The earlier same-session `C0/I0/M0` statement is therefore not a valid
semantic disposition and must not be used for acceptance.

A second detached review of exact repair source
`f83338649415b567964d8e1328fe3dc6a32ac8b5` then returned `C0/I3/M0`. It
demonstrated that a response-scoped event queued after `response.done` bypasses
inspection after PCM release; recognition audio, commit and even final output
can race ahead of strict native session validation; and `response.created`
accepts contradictory conversation, modality, status, voice and audio-format
facts that a later terminal event can overwrite. The second repair is limited
to terminal quarantine/drain, a negotiated recognition data-plane fence and a
complete initial response validator, with matching concurrency and zero-effect
oracles. That second repair and its affected automated matrix now pass, but no
independent reviewer has inspected the repaired source. A third detached review
is required before any real Provider/device validation. No OpenAI credential,
network session, microphone or speaker was used, so all physical claims remain
open. No prior source/automation statement grants current PASS or independent
review credit.

The review covers the change based on
`2d06fd37822c6a20ac8185fbe7cd3df7900cf4bc`; the containing commit is the
reviewed delivery source.

## Intended behaviour and owned surfaces

The optional Adapter is selected only by
`LIVE_VOICE_SPEECH_PROVIDER=openai-realtime` while the existing formal
streaming flag is enabled. It keeps API credentials in the Gateway process and
uses server-to-server Realtime WebSockets. The current voice-agent model
default is `gpt-realtime-1.5`; a compatible `gpt-realtime` family member can be
selected with `LIVE_VOICE_SPEECH_REALTIME_MODEL`.

Owned surfaces:

- [`openai_streaming_speech.py`](../../jiuwenswarm/server/live_voice/openai_streaming_speech.py)
  for configuration, session negotiation, Realtime event handling, exact
  identity fencing, bounded audio buffering, cancellation and degradation;
- focused Provider conformance tests and the affected Gateway synthesis route;
- [D-095](../decisions/DECISIONS.md) and synchronized capability status.

The existing `LIVE_VOICE_SPEECH_PROVIDER=openai` Realtime-transcription plus
Audio Speech TTS cascade is preserved. Browser-to-Provider transport,
Provider-native JiuwenSwarm tool calls, Provider-authored product answers,
committed-final or Runtime fence bypass, continuous cross-turn native duplex,
default-on rollout, billing/key changes, physical acceptance, deployment and
remote-ref updates are excluded.

## Protocol and authority judgement

The implementation follows the official
[Realtime WebSocket guide](https://developers.openai.com/api/docs/guides/realtime-websocket),
[Realtime conversations guide](https://developers.openai.com/api/docs/guides/realtime-conversations),
[`gpt-realtime-1.5` model page](https://developers.openai.com/api/docs/models/gpt-realtime-1.5)
and [model catalog](https://developers.openai.com/api/docs/models).

Recognition uses a native Realtime session with PCM input, optional input
transcription and server/manual VAD, but disables automatic response creation
and Provider interruption. Only an exact final transcript can enter the
existing committed-input path; the Adapter itself has zero Agent, Tool, Task
and history authority.

Synthesis sends already-authoritative JiuwenSwarm Agent `spoken_text` in an
out-of-band `response.create` with `conversation="none"`, empty input, no tools
and string-valued exact response/generation/unit metadata. Since instructions
are not an authority guarantee, audio remains in an 8 MiB bounded buffer until
the output transcript, response/item/content identity, completed message
shape, audio format and voice all match exactly. Changed text, malformed audio,
cross-response events, late/duplicate events, a downgraded session, non-audio
terminal output, timeout or cancellation releases zero buffered audio and
publishes the existing visible degradation truth.

The model is selected only in the WebSocket URL. Effective `session.updated`
truth is validated rather than trusting the request. Cancellation is bound to
the exact Provider response and transport close is not treated as a Provider
cancel acknowledgement.

Because complete output must pass transcript gating before release, this
Adapter receives no streaming first-audio latency credit and is not claimed as
continuous native duplex.

## Applicable Tier-3 matrix

| Dimension | Evidence and judgement |
|---|---|
| `P` positive | Native recognition negotiation/final and exact native synthesis reach the existing product downlink. |
| `N` negative | Invalid model/configuration, changed text, non-audio output, malformed audio and downgraded sessions fail closed. |
| `B` boundary | PCM/rate/model family, provider delta, stream buffer, text, queue and timeout bounds remain explicit. |
| `S` stale/replay | A bounded server-event-ID ledger plus exact response/item/output/content and existing response/generation/unit identities reject replay, cross-response and stale data. |
| `T` timeout/retry | An explicit response lifecycle rejects illegal terminal order; valid progress alone renews the bounded progress deadline. Connect/send/receive/cleanup remain bounded. |
| `C` concurrency/cancel | Exact response cancel is emitted when known; local/transport completion does not forge cancel acknowledgement. |
| `R` restart/reconnect | Each synthesis unit owns a separate bounded socket; no conversational state is silently resumed or inferred. |
| `I` isolation | Credentials stay Gateway-private; native effective VAD controls must be strict booleans set to false, effective translate/whisper purpose changes fail closed, and the Adapter cannot invoke Agent/Tool/Task/history authority. |
| `F` forbidden effects | Partial, mismatched, malformed, tool-shaped and failed paths assert zero Agent, Tool, Task and history effects and zero audio release. |
| `K` compatibility | A production Web-factory composition test covers native selection, invalid-config TEXT fallback and flag-off; the existing `openai` cascade and provider-neutral route retain regression coverage. |
| `X` observability/privacy | Provider/config facts are content-free, secrets stay out of repr/errors, and degradation remains typed and visible. |

## Repair response to the independent findings

The repair is deliberately limited to the four reported findings:

1. **I1 — replay/order/progress:** every native synthesis server event now
   requires a unique bounded `event_id`; negotiation and response events move
   through explicit created/item/content/audio/transcript/terminal phases; only
   valid protocol progress renews the whole-response progress deadline. Replay,
   transcript-before-audio completion, audio-after-done, premature terminal,
   missing event ID, exact ledger saturation and no-progress event flood tests
   all fail before audio release and assert zero Agent/Tool/Task/history effects.
2. **I2 — native VAD authority:** native Realtime server-VAD negotiation now
   requires both `create_response` and `interrupt_response` to be present,
   exactly `bool`, and exactly `False`. Missing, `None`, `0` and `True` fail
   closed; the older transcription-only omission compatibility test still
   passes.
3. **I3 — effective model purpose:** configuration and effective session echoes
   share one predicate. Exact/generic voice aliases remain supported while
   `gpt-realtime-translate*` and `gpt-realtime-whisper*` are rejected for both
   recognition and synthesis.
4. **M1 — persistent composition/bounds:** the real production Web factory now
   has native, invalid-config and flag-off selection oracles. Audio tests cover
   exact `96,000`-byte delta acceptance versus `96,002` rejection and exact
   8 MiB aggregate acceptance versus `+2` rejection.

These are implementer-run repair results, not an independent follow-up
disposition. The second independent `C0/I3/M0` result remains the latest
independent judgement until a detached reviewer inspects the second repair.

## Second repair response to the second independent findings

The second repair is deliberately limited to the three reported Important
findings:

1. **I1 — terminal quarantine:** `response.done` moves the response to a
   terminal phase without publishing PCM. A bounded terminal drain accepts
   unique-ID `rate_limits.updated` control events without progress renewal,
   rejects any response-scoped late event, and requires successful transport
   close before releasing the exact buffered audio. The positive oracle proves
   close-before-first-chunk and exact sample count; the queued late-delta oracle
   proves zero audio, exactly one protocol degradation and zero business effects.
2. **I2 — recognition negotiation fence:** the opening session remains in the
   registry so cancel/close can find it, but audio send, manual commit and output
   reads fail with `RECOGNITION_SESSION_NOT_NEGOTIATED` until strict effective
   VAD/session validation succeeds. All eight invalid VAD echoes exercise those
   three concurrent data-plane calls, and a Provider final emitted before
   negotiation fails with turn-order protocol truth and zero business effects.
3. **I3 — complete initial response binding:** `response.created` now requires
   the initial `realtime.response` to be `in_progress`, have empty output, null
   conversation, audio-only modality, exact metadata, PCM 24 kHz output and the
   configured voice before any later lifecycle event is accepted. Contradictory
   conversation, modality, status, output, voice, format and missing required
   fields each release zero audio and emit one protocol degradation.

These results are still implementer-run source/automation evidence. They do not
change the last independent FAIL or authorize physical/provider acceptance.

## Verification

Executed in the second-repair worktree on Windows after the second independent
findings:

```text
uv run pytest -q -o addopts="" tests\unit_tests\live_voice\test_openai_streaming_speech.py --cov=jiuwenswarm.server.live_voice.openai_streaming_speech --cov-report=term
116 passed in 5.46s; openai_streaming_speech.py 1864 statements, 210 missed, 89%

uv run pytest -q --no-cov tests\unit_tests\live_voice\test_streaming_speech.py tests\unit_tests\gateway\test_streaming_speech_route.py tests\unit_tests\gateway\test_streaming_synthesis_route.py tests\unit_tests\gateway\test_product_streaming_synthesis.py --deselect tests/unit_tests/gateway/test_streaming_synthesis_route.py::test_cancel_api_caller_cancel_retries_cleanup_then_rethrows
171 passed, 1 deselected in 5.27s

C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe -m pytest -q -o addopts="" tests\unit_tests\test_app_web_handlers.py
80 passed in 11.03s

uv run ruff check jiuwenswarm\server\live_voice\openai_streaming_speech.py tests\unit_tests\live_voice\test_openai_streaming_speech.py tests\unit_tests\gateway\test_streaming_synthesis_route.py tests\unit_tests\test_app_web_handlers.py
PASS

uv run ruff format --check jiuwenswarm\server\live_voice\openai_streaming_speech.py tests\unit_tests\live_voice\test_openai_streaming_speech.py tests\unit_tests\gateway\test_streaming_synthesis_route.py
3 files already formatted

uv run mypy --follow-imports=skip --ignore-missing-imports jiuwenswarm\server\live_voice\openai_streaming_speech.py
Success: no issues found in 1 source file

uv run python -m py_compile jiuwenswarm\server\live_voice\openai_streaming_speech.py tests\unit_tests\live_voice\test_openai_streaming_speech.py tests\unit_tests\gateway\test_streaming_synthesis_route.py tests\unit_tests\test_app_web_handlers.py
PASS

git diff --check
PASS
```

The deselected Gateway test,
`test_cancel_api_caller_cancel_retries_cleanup_then_rethrows`, fails with the
same `handle.cleanup_complete is False` assertion on both this worktree and the
unchanged base worktree. It is an inherited baseline failure and does not
exercise the new native Realtime Adapter. It is recorded rather than hidden or
reclassified as a pass.

The repository's existing Python 3.11 environment collected and passed all 80
Web-factory tests. The focused and affected speech matrices used Python 3.13.

## Cold complete-diff review

The same-session substitute review corrected these issues before the final
matrix:

1. changed the default from the deprecated `gpt-realtime` alias to current
   `gpt-realtime-1.5`;
2. removed `model` from `session.update`, keeping model selection in the
   WebSocket URL and validating the effective echo;
3. converted Realtime metadata values to strings;
4. corrected the formal Provider capability classification;
5. bounded buffered-audio release without constructing an unbounded sample
   list;
6. rejected audio after audio completion and required exact terminal output,
   message, content, format, voice and transcript truth;
7. bounded exact `response.cancel` sending and added a negative oracle for
   terminal function/tool-shaped output.

That historical substitute-review result was **`C0/I0/M0`**, but the subsequent
independent `C0/I3/M1` result superseded it. It is retained only to explain the
review sequence and grants no current acceptance credit.

## Activation contract and remaining trigger

```dotenv
LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED=true
LIVE_VOICE_SPEECH_PROVIDER=openai-realtime
LIVE_VOICE_SPEECH_API_BASE=https://api.openai.com/v1
LIVE_VOICE_SPEECH_API_KEY=<gateway-private-key>
LIVE_VOICE_SPEECH_REALTIME_MODEL=gpt-realtime-1.5
LIVE_VOICE_SPEECH_STT_MODEL=gpt-4o-mini-transcribe
LIVE_VOICE_SPEECH_TTS_VOICE=marin
```

The next acceptance trigger is a detached independent Tier-3 follow-up review
of the exact repair commit and its complete boundary. Only after that review
passes may a shortest real server-to-server probe be followed by the existing
microphone/Agent/playout journey. The physical run must record Provider/session
model truth, final transcript, audible exact Agent text, cancel/degradation
behaviour and fixed-corpus latency, and must not reuse the API key in browser
state, logs or evidence.
