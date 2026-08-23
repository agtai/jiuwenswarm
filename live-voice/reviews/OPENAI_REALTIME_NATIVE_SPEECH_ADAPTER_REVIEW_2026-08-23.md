# OpenAI Realtime native Speech Adapter review — 2026-08-23

## Disposition

**SOURCE/AUTOMATION PASS — PHYSICAL PROVIDER AND INDEPENDENT-REVIEW CREDIT
UNCLAIMED.**

The coherent Tier-3 implementation and affected automated matrix pass. A
same-session cold complete-diff review found and corrected protocol and
authority defects, with no remaining actionable finding (`C0/I0/M0`) in that
substitute review. It is not independent review under the repository rule, so
this document does not close that acceptance dimension. No OpenAI credential,
network session, microphone or speaker was available; real Provider, device,
quality and latency claims also remain open.

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
| `S` stale/replay | Exact response/item/output/content and existing response/generation/unit identities reject cross-response and stale data. |
| `T` timeout/retry | Event/connect/send/receive/cleanup operations are bounded; timeout degrades visibly without business effects. |
| `C` concurrency/cancel | Exact response cancel is emitted when known; local/transport completion does not forge cancel acknowledgement. |
| `R` restart/reconnect | Each synthesis unit owns a separate bounded socket; no conversational state is silently resumed or inferred. |
| `I` isolation | Credentials stay Gateway-private; the Adapter cannot invoke Agent/Tool/Task/history authority. |
| `F` forbidden effects | Partial, mismatched, malformed, tool-shaped and failed paths assert zero Agent, Tool, Task and history effects and zero audio release. |
| `K` compatibility | The existing `openai` cascade, provider-neutral route and flag-off/fallback behaviour retain regression coverage. |
| `X` observability/privacy | Provider/config facts are content-free, secrets stay out of repr/errors, and degradation remains typed and visible. |

## Verification

Executed in the independent worktree on Windows:

```text
uv run pytest -q --no-cov tests\unit_tests\live_voice\test_openai_streaming_speech.py
83 passed in 2.94s

uv run pytest -q -o addopts="" tests\unit_tests\live_voice\test_openai_streaming_speech.py --cov=jiuwenswarm.server.live_voice.openai_streaming_speech --cov-report=term-missing
83 passed; openai_streaming_speech.py 1716 statements, 212 missed, 88%

uv run pytest -q --no-cov tests\unit_tests\live_voice\test_streaming_speech.py tests\unit_tests\gateway\test_streaming_speech_route.py tests\unit_tests\gateway\test_streaming_synthesis_route.py tests\unit_tests\gateway\test_product_streaming_synthesis.py --deselect tests/unit_tests/gateway/test_streaming_synthesis_route.py::test_cancel_api_caller_cancel_retries_cleanup_then_rethrows
171 passed, 1 deselected in 4.19s

C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe -m pytest -q -o addopts="" tests\unit_tests\test_app_web_handlers.py
79 passed in 6.48s

uv run ruff check jiuwenswarm\server\live_voice\openai_streaming_speech.py tests\unit_tests\live_voice\test_openai_streaming_speech.py tests\unit_tests\gateway\test_streaming_synthesis_route.py
PASS

uv run mypy --follow-imports=skip --ignore-missing-imports jiuwenswarm\server\live_voice\openai_streaming_speech.py
Success: no issues found in 1 source file

uv run python -m py_compile jiuwenswarm\server\live_voice\openai_streaming_speech.py tests\unit_tests\live_voice\test_openai_streaming_speech.py tests\unit_tests\gateway\test_streaming_synthesis_route.py
PASS
```

The deselected Gateway test,
`test_cancel_api_caller_cancel_retries_cleanup_then_rethrows`, fails with the
same `handle.cleanup_complete is False` assertion on both this worktree and the
unchanged base worktree. It is an inherited baseline failure and does not
exercise the new native Realtime Adapter. It is recorded rather than hidden or
reclassified as a pass.

Python 3.13 cannot collect the Web-factory file because the installed
third-party `pysbd` release contains an invalid escape rejected by that Python
version. The repository's existing Python 3.11 environment collected and
passed all 79 Web-factory tests.

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

Final substitute-review result: **`C0/I0/M0`**. The reviewer and implementer
were the same session, so an independent reviewer must still inspect the
complete commit before repository rules permit independent-review credit.

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

The next acceptance trigger is a shortest real server-to-server probe followed
by the existing microphone/Agent/playout journey on the exact committed source.
It must record Provider/session model truth, final transcript, audible exact
Agent text, cancel/degradation behaviour and fixed-corpus latency. That run
must not reuse the API key in browser state, logs or evidence.
