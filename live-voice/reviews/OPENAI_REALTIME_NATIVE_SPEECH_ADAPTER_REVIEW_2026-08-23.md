# OpenAI Realtime native Speech Adapter review — 2026-08-23

## Disposition

**SOURCE/AUTOMATION/INDEPENDENT REVIEW PASS — REAL PROVIDER PROBE NEXT.**

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
oracles. That second repair and its affected automated matrix passed implementer
checks; at that point a third detached review was required before any real
Provider/device validation. No OpenAI credential,
network session, microphone or speaker was used, so all physical claims remain
open. No prior source/automation statement grants current PASS or independent
review credit.

A third detached review of exact second-repair source
`21d3de2a4d05c5885f6c482856ec0f03bd835370` returned `C0/I4/M0`. It proved
that a response-scoped frame received during the socket close handshake can
escape the fixed terminal quarantine; opening recognition cancel does not
settle `ready` and therefore emits a later false timeout; terminal
`response.done` accepts contradictory object, status-details and usage facts;
and native recognition accepts missing or replayed server event IDs without a
bounded ledger. The third repair is limited to those four protocol/lifecycle
seams and their exact positive, negative, concurrency, boundary and forbidden-
effect oracles. Its source and affected automated matrix passed implementer
checks and then advanced to a fourth detached review.

That fourth review of exact third-repair source
`e3664e798fe9901c3bbdd69a140f51bca6542e4a` returned `C0/I2/M0`. It closed
the prior close-handshake, terminal-resource and recognition-event-ID findings,
but proved that close-induced EOF can still make the recognition worker settle
an opening session before its cancel owner, producing stale conformance and the
wrong degradation fact. It also proved the strict local initial-resource
contract accepts omitted `status_details` and `usage` as if they were explicit
null. The fourth repair was limited to those two lifecycle/resource-presence
seams and their exact concurrency, process-control and zero-effect oracles. Its
source and affected automation passed, but the repeated repair structure left
recognition terminal ownership distributed across cancel, receive, rollback,
send failure and Provider close. Consolidated source
`1d4f067cf697c4773b3ec7f0cfba307a9238594e` replaces those parallel terminal
paths with one shielded per-session finalization task and replaces duplicated
initial/terminal response-field sets with one shared contract.

A detached review then inspected exact clean source
`cdb88eb0ae81a32aadb58c0aaf92e838e21206b1` and returned **`C0/I3/M1`**. It
confirmed the earlier findings closed, but proved four remaining lifecycle
interleavings: an already-queued valid negotiation frame could win after cancel
marked recognition closing; normal recognition final still bypassed the shared
terminal owner; synthesis cleanup could be interrupted by a cancelled waiter or
observability process-control; and an opening receive-owned process-control had
two observable throw surfaces.

Repair source `2698bd9b811f3fe6a710cbbb8c132dd4a9ed2861` closed those findings as
one lifecycle convergence. A later complete-module review of exact
`6224f8e27fa1ba4508f08e4820c4871ba162c8a2` found one shared boolean transport-
settlement defect, repaired by `6aed58f5bce5fdfed3bc2920937af377ebafddc3`.
The required targeted review of exact clean docs HEAD
`e6663dfa8c6e0fcac88b91ee3fcd1be2f6d45aef` then returned **`C0/I1/M0`**. It
confirmed every session-backed lifecycle path, but found that recognition's
socket-allocated, pre-session failed-open rollback still called close directly
once and could skip retry, conformance reaping and degradation truth.

Product/test source `87b57a69cdb0ffd496468092463ebcf926fb6a10`
connects that last entry to the existing `_FinalizationFailures` and two-attempt
socket settlement. It settles resource, conformance and the unique open-failure
fact before applying process-control, cancellation, cleanup and original-
failure priority. It adds no session or second finalization task. The final
detached targeted review of exact clean docs HEAD
`688ae114942ecd26bcfff8b37effe7ebb59998d9` returned
**PASS — `C0/I0/M0`**. It confirmed only this entry and the shared-helper
regression, so the source/automation/independent-review Gate is closed without
restarting the completed module review. No physical credit exists.

The cumulative review boundary is based on
`2d06fd37822c6a20ac8185fbe7cd3df7900cf4bc`; the current product/test repair
source is exact commit `87b57a69cdb0ffd496468092463ebcf926fb6a10`.

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
| `C` concurrency/cancel | Queued negotiation, queue-full normal final, cancelled terminal waiter, retry and process-control interleavings share one first terminal owner; exact response cancel is emitted when known and local/transport completion does not forge cancel acknowledgement. |
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
disposition. At that historical stage the then-latest independent judgement
remained `C0/I2/M0` pending review of the fourth repair.

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

## Third repair response to the third independent findings

The third repair is deliberately limited to the four reported Important
findings:

1. **I1 — close-handshake receive authority:** after the bounded terminal
   quarantine, one drain task owns receive before local close begins. Buffered
   PCM is published only after close succeeds and the production WebSocket
   wrapper proves terminal receive EOF. A unique late response delta delivered
   during close releases zero audio and emits one protocol fact; a unique
   `rate_limits.updated` event in the same window remains legal.
2. **I2 — opening cancel settlement:** external recognition cancel closes and
   retires the registered opening session, records the single unacknowledged-
   cancel fact, and then settles its shielded `ready` future. The opening call
   wakes as cancellation within the bounded oracle and cannot later add a false
   Provider-timeout fact.
3. **I3 — complete terminal response truth:** `response.done` now requires the
   complete terminal `realtime.response` shape, null status-details and a
   nonnegative, internally consistent usage resource before any buffered PCM
   can be released. Missing, mistyped, contradictory and arithmetically invalid
   terminal facts fail closed.
4. **I4 — recognition event identity:** every server event on the native
   recognition route requires a safe unique `event_id` in the same bounded
   per-session ledger used for native synthesis. Missing IDs, replay across the
   speech-start/stop/commit/final lifecycle and ledger overflow emit protocol
   degradation and cannot release a recognition final.

These are implementer-run source/automation results only. They do not change
the latest independent FAIL or authorize physical/provider acceptance.

## Fourth repair response to the fourth independent findings

The fourth repair is deliberately limited to the two reported Important
findings:

1. **I1 — opening cancel/EOF ownership:** each recognition session now
   serializes cancel owners. Once an owner marks the session closing, the
   receive worker cannot mutate `ready`, conformance or registry state for EOF,
   transport failure or cancellation. The cancel owner closes transport,
   settles the worker, closes and reaps conformance, retires the registry entry,
   emits exactly one unacknowledged-cancel fact and only then releases the
   opening waiter. Concurrent duplicate cancel is idempotent for the retained
   session; process-control is preserved only after the same cleanup barrier.
   Exact EOF and generic-worker-failure orderings prove one conformance close,
   one cancel fact, prompt opening cancellation and zero business effects.
2. **I2 — initial nullable-field presence:** the strict local initial
   `realtime.response` validator now requires both `status_details` and `usage`
   keys in addition to requiring their values to be null. Omitting either key
   emits one protocol degradation and releases zero PCM or completion.

These are implementer-run source/automation results only. They do not change
the latest independent FAIL or authorize physical/provider acceptance.

## Consolidation after the serial repair cycle

The consolidation is a behaviour-preserving ownership refactor plus stronger
contract mutation coverage, not another finding-by-finding product expansion:

1. **One terminal owner:** cancel, Provider failure, failed-open rollback and
   Provider close synchronously install or reuse one `finalization_task` on the
   recognition session. All contenders await that exact task through
   `asyncio.shield`; cancelling one waiter cannot cancel shared cleanup.
2. **One settlement sequence:** the owner alone closes transport, settles the
   receive worker when it is not the origin, closes/reaps conformance, retires
   the exact registry entry, emits the applicable content-free fact and settles
   opening `ready` last. Receive-owned failures retain close as the visible
   post-observability barrier; external owners close first to wake receive.
3. **Explicit cause matrix:** `cancel`, `provider_failure`, `rollback` and
   `service_close` select only the cause-specific conformance, observability and
   ready outcome. Mechanical cleanup is shared. Process-control is returned
   only after the same cleanup barrier.
4. **One response resource contract:** initial and terminal validators share
   the same ten required fields. Both negative suites delete every field in the
   table and require one protocol degradation with zero PCM/business effects.
5. **Measured reduction:** target-module statements fall from `2041` to `2029`;
   direct recognition conformance-close call sites fall from six to two; and
   `cancel_recognition` falls from about 95 lines to a small delegating entry
   point. The longer shared runner replaces four independent terminal
   algorithms rather than adding a fifth.

This source/automation result intentionally resets review to one cold complete
module-boundary review. The reviewer must assess the final state machine and
all first-owner interleavings, not replay the historical review numbering or
grant/withhold credit based on the number of prior rounds.

## Lifecycle convergence after the consolidated review

The post-consolidation repair addresses the two root causes exposed by the
`cdb88eb0` review rather than adding four isolated exception branches:

1. **Normal success is a terminal cause.** Recognition `normal_final` owns
   socket close and bounded FINAL publication inside the installed finalizer.
   Synthesis `normal_complete` similarly owns transport settlement, tail and
   COMPLETED publication. A concurrent cancel or service close waits for that
   first owner and cannot overwrite an accepted terminal result.
2. **Synthesis has the same non-cancellable terminal ownership as
   recognition.** Cancel, Provider failure, failed-open rollback and service
   close synchronously install or reuse one finalization task. All public
   waiters use `shield`; the owner clears buffered native PCM and settles
   transport, worker, conformance, registry and degradation truth before it
   returns process-control or cleanup failure.
3. **Opening recognition has one outcome surface.** Once closing is visible, a
   frame returned from `recv` is fenced before parsing or `ready` mutation. A
   receive-owned failure during opening completes its private worker normally
   after finalization; `open_recognition` remains the sole public throw surface.
4. **Exact race oracles replace timing luck.** Coordinated close fakes and a
   deliberately full 64-event queue reproduce the valid queued negotiation,
   accepted-FINAL/cancel, cancelled synthesis waiter/retry and protocol-failure
   plus sink-process-control windows. They assert one terminal owner, retained
   final or degradation truth, complete cleanup and zero Agent/Tool/Task/history
   effects.

This remains one bounded lifecycle module repair. It introduces no schema,
Agent/Tool/Task/history authority, deployment, credential, device or product
policy change.

## Verification

Executed on exact source `2698bd9b811f3fe6a710cbbb8c132dd4a9ed2861` in the
dedicated Windows worktree after the lifecycle convergence:

```text
.venv\Scripts\python.exe -m pytest -q -o addopts="" tests\unit_tests\live_voice\test_openai_streaming_speech.py --cov=jiuwenswarm.server.live_voice.openai_streaming_speech --cov-report=term
155 passed in 5.71s; openai_streaming_speech.py 2098 statements, 273 missed, 87%

.venv\Scripts\python.exe -m pytest -q --no-cov tests\unit_tests\live_voice\test_streaming_speech.py tests\unit_tests\gateway\test_streaming_speech_route.py tests\unit_tests\gateway\test_streaming_synthesis_route.py tests\unit_tests\gateway\test_product_streaming_synthesis.py --deselect tests/unit_tests/gateway/test_streaming_synthesis_route.py::test_cancel_api_caller_cancel_retries_cleanup_then_rethrows
171 passed, 1 deselected in 7.96s

C:\Users\admin\Desktop\live voice hx\.venv\Scripts\python.exe -m pytest -q -o addopts="" tests\unit_tests\test_app_web_handlers.py
80 passed in 12.81s

.venv\Scripts\python.exe -m ruff check jiuwenswarm\server\live_voice\openai_streaming_speech.py tests\unit_tests\live_voice\test_openai_streaming_speech.py tests\unit_tests\gateway\test_streaming_synthesis_route.py tests\unit_tests\test_app_web_handlers.py
PASS

.venv\Scripts\python.exe -m ruff format --check jiuwenswarm\server\live_voice\openai_streaming_speech.py tests\unit_tests\live_voice\test_openai_streaming_speech.py tests\unit_tests\gateway\test_streaming_synthesis_route.py
3 files already formatted

.venv\Scripts\python.exe -m mypy --follow-imports=skip --ignore-missing-imports jiuwenswarm\server\live_voice\openai_streaming_speech.py
Success: no issues found in 1 source file

.venv\Scripts\python.exe -m py_compile jiuwenswarm\server\live_voice\openai_streaming_speech.py tests\unit_tests\live_voice\test_openai_streaming_speech.py tests\unit_tests\gateway\test_streaming_synthesis_route.py tests\unit_tests\test_app_web_handlers.py
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
Web-factory tests. The consolidation worktree's Python 3.13 environment cannot
collect that suite because its inherited `pysbd` package contains a Python-3.13
invalid escape; this is an environment/dependency incompatibility, not a hidden
Web pass. The focused and affected speech matrices used Python 3.13.

## Transport settlement finding and root-cause repair

The required detached complete-module review of exact clean HEAD
`6224f8e27fa1ba4508f08e4820c4871ba162c8a2` returned **`C0/I1/M0`**. It closed
all earlier findings and isolated one remaining shared defect: the session
finalizer ignored the legitimate boolean `False` returned by transport cleanup.
That allowed recognition FINAL to be published while the socket-close task was
only retained, and allowed close-side process-control to escape public cancel
before a session-local retry and the required degradation fact.

Source `6aed58f5bce5fdfed3bc2920937af377ebafddc3` repairs that one settlement
boundary. `_FinalizationFailures.settle` now preserves typed incomplete truth;
recognition and synthesis use the same two-attempt finalizer-owned transport
settlement; bounded failure becomes `SPEECH_PROVIDER_CLEANUP_INCOMPLETE` rather
than a false terminal success. Cancellation and ordinary failure facts are
settled even when cleanup has stored a later process-control outcome. Exact
oracles prove that a blocked recognition close releases no FINAL, while both
recognition and synthesis retry a one-shot close `GeneratorExit`, close on the
second attempt, retain one cancellation fact and only then rethrow. No
Agent/Tool/Task/history or unauthorized PCM effect is introduced.

Executed on exact source `6aed58f5bce5fdfed3bc2920937af377ebafddc3`:

```text
.venv\Scripts\python.exe -m pytest -q -o addopts="" tests\unit_tests\live_voice\test_openai_streaming_speech.py --cov=jiuwenswarm.server.live_voice.openai_streaming_speech --cov-report=term
158 passed in 7.52s; openai_streaming_speech.py 2111 statements, 275 missed, 87%

.venv\Scripts\python.exe -m pytest -q --no-cov tests\unit_tests\live_voice\test_streaming_speech.py tests\unit_tests\gateway\test_streaming_speech_route.py tests\unit_tests\gateway\test_streaming_synthesis_route.py tests\unit_tests\gateway\test_product_streaming_synthesis.py --deselect tests/unit_tests/gateway/test_streaming_synthesis_route.py::test_cancel_api_caller_cancel_retries_cleanup_then_rethrows
171 passed, 1 deselected in 8.82s

.venv\Scripts\python.exe -m pytest -q -o addopts="" tests\unit_tests\test_app_web_handlers.py
80 passed in 17.12s

Ruff check/format, targeted mypy, py_compile and git diff --check
PASS
```

The deselected Gateway baseline still fails independently at
`handle.cleanup_complete is True` with actual `False`; this repair does not
touch that route. These are implementer-run source/automation results, not an
independent PASS. The resulting targeted review was performed at exact docs
HEAD `e6663dfa`; its one omitted pre-session entry and repair are recorded
below.

## Pre-session failed-open settlement finding and repair

The detached targeted review of exact clean HEAD
`e6663dfa8c6e0fcac88b91ee3fcd1be2f6d45aef` returned **`C0/I1/M0`**. It
confirmed that normal final/complete, caller cancel, Provider failure, timeout,
session-backed rollback and service close all use the shared session
settlement. Its sole finding was a socket allocated immediately before
`_StreamingLinearResampler` construction failed: because no session existed,
`_rollback_failed_recognition()` called `_close_socket()` directly once.

That path could therefore publish the original
`SPEECH_PROVIDER_TRANSPORT_UNAVAILABLE` while a non-cooperative socket remained
retained, or expose a first close `GeneratorExit` with one close attempt,
active/retained conformance identity and no degradation fact. It was one missed
entry into the already accepted resource helper, not a new protocol or
lifecycle design finding.

Product/test source `87b57a69cdb0ffd496468092463ebcf926fb6a10` passes one
`_FinalizationFailures` accumulator from `open_recognition()` into rollback.
The pre-session branch now uses `_settle_finalization_socket()` for the same
bounded two attempts, records any conformance settlement failure, always reaps
terminal identity, settles exactly one ordinary open-failure fact, and only
then selects process-control, cancellation, cleanup or the original open
failure. Session-backed rollback records its existing finalizer outcome in the
same accumulator. No second task, session, retry loop, protocol state or
business authority was introduced.

Executed on exact product/test source
`87b57a69cdb0ffd496468092463ebcf926fb6a10`:

```text
uv run python -m pytest -q -o addopts="" tests/unit_tests/live_voice/test_openai_streaming_speech.py --cov=jiuwenswarm.server.live_voice.openai_streaming_speech --cov-report=term
160 passed in 6.30s; openai_streaming_speech.py 2124 statements, 276 missed, 87%

uv run python -m pytest -q --no-cov tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/gateway/test_streaming_speech_route.py tests/unit_tests/gateway/test_streaming_synthesis_route.py tests/unit_tests/gateway/test_product_streaming_synthesis.py --deselect tests/unit_tests/gateway/test_streaming_synthesis_route.py::test_cancel_api_caller_cancel_retries_cleanup_then_rethrows
171 passed, 1 deselected in 10.60s

uv run ruff check jiuwenswarm/server/live_voice/openai_streaming_speech.py tests/unit_tests/live_voice/test_openai_streaming_speech.py
uv run ruff format --check jiuwenswarm/server/live_voice/openai_streaming_speech.py tests/unit_tests/live_voice/test_openai_streaming_speech.py
uv run mypy --follow-imports=skip --ignore-missing-imports jiuwenswarm/server/live_voice/openai_streaming_speech.py
uv run python -m py_compile jiuwenswarm/server/live_voice/openai_streaming_speech.py tests/unit_tests/live_voice/test_openai_streaming_speech.py
git diff --check
PASS
```

The two new event-driven oracles use the existing non-cooperative and one-shot
process-control socket fakes and replace the resampler constructor only in
memory after socket allocation. They assert public cleanup truth, two close
attempts where applicable, zero active/retained identity, one exact
`recognition.open` fact, clean registry/opening ownership and zero FINAL/PCM/
Agent/Tool/Task/history effect. No arbitrary sleep is used. The unchanged Web
factory composition and inherited deselected Gateway assertion were not rerun:
the repair does not reach either seam, and the targeted reviewer had just
confirmed the latter fails identically on baseline and candidate.

The final detached confirmation used exact clean docs HEAD
`688ae114942ecd26bcfff8b37effe7ebb59998d9` and returned
**PASS — `C0/I0/M0`**. It ran only the two pre-session oracles plus the existing
cancelled-registration, mechanical-final and parameterized recognition/
synthesis shared-settlement regressions:

```text
uv run python -m pytest -q -o addopts="" tests/unit_tests/live_voice/test_openai_streaming_speech.py::test_failed_open_without_session_reports_incomplete_socket_settlement tests/unit_tests/live_voice/test_openai_streaming_speech.py::test_failed_open_without_session_retries_close_before_process_control tests/unit_tests/live_voice/test_openai_streaming_speech.py::test_cancelled_recognition_registration_rolls_back_exact_session tests/unit_tests/live_voice/test_openai_streaming_speech.py::test_native_realtime_final_requires_mechanical_transport_settlement tests/unit_tests/live_voice/test_openai_streaming_speech.py::test_session_cancel_retries_close_before_process_control_and_fact
6 passed in 5.01s
```

The exact Ruff check, Ruff format check, targeted mypy, `py_compile` and both
requested range `git diff --check` commands passed. Start and finish were clean
detached HEAD in
`C:\Users\admin\Desktop\live voice hx-openai-realtime-final-confirm-688ae114-20260824`;
the branch ref matched, `git diff --exit-code` returned zero, and no untracked
file, candidate mutation, commit, ref update or push occurred. The review did
not expand to full Provider, Gateway, Web, project or real-device tests. It
therefore closes only the source/automation/independent-review Gate and does not
grant Provider, network, device, audibility, latency or quality credit.

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

The source/automation/independent-review Gate is closed. The next acceptance
trigger is a separately scoped shortest real server-to-server probe on the
current exact candidate, using the Gateway-held standard API key boundary in
the official Realtime WebSocket guide. It first proves real connection,
effective session/model truth, one committed recognition final, exact
authoritative-text synthesis, bounded cancel/degradation and clean transport
settlement without a browser or physical device claim. Only after that passes
may the existing microphone/Agent/playout journey and fixed-corpus latency run
begin. Secrets and raw Provider payloads remain outside Git, logs and evidence;
billing/account/project changes, browser-held credentials and public deployment
remain excluded.
