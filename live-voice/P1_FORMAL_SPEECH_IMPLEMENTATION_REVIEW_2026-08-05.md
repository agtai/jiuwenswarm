# P1 formal batch Speech implementation review

> Task: `P1-SR-B-SS-B`
>
> Batch date: 2026-08-05
>
> Branch/worktree: `codex/lv-p1-formal-speech` / independent worktree from `1e76dbd6aa0ebb011842f31beb98ca2cb11d2496`
>
> Preserved reviewed candidate: `cea69737cc445ca68db06d8bf6b4d23babcdf70c`; the integration-review remediation described below is an uncommitted candidate on top of that commit.
>
> Record role: package-local implementation/review evidence only. Landed state, product composition, release state and Replacement Ledger credit remain owned by the Integration Owner and `STATUS.md`.

## 1. Bounded outcome

This batch adds the formal, batch-only `SR-B/SS-B` Adapter and package-local Gateway RPC contract. Final AIO-B frames can be converted into one bounded mono PCM16 WAV recognition request; a server-authorized exact Agent render binding can produce bounded mono PCM16 WAV synthesis output and ordered Float32 chunks for AIO-B playout. Both results retain formal Provider/model provenance.

The current Web connection supplies only `request_asserted` identity. That assurance proves request consistency, not authentication or tenant/operation authorization. No authentication attempt or authenticated identity source exists on this path, so this is an absence of authentication—not a failed authentication of the asserted `user_id`. The default Gateway route therefore rejects before any external Provider call even when Provider credentials are configured. Formal product composition is **BLOCKED** until the Integration Owner supplies a trusted authenticated identity source and server-owned exact authorization resolver. This is a fail-closed backend foundation, not a runnable formal Web route.

The frontend client is dependency-injected and is not imported by `useLiveVoiceDemo`, `integratedP1Route` or another final Web product entry. Existing Browser Speech recognition/synthesis stays the explicit compatibility fallback. Recognition final remains evidence and carries `commits_turn=false`; synthesis output carries `presented=false` until AIO-B acknowledges browser rendering. This is a real SR-B/SS-B package, not a claim that AIO-B alone, cumulative P1 or the Integrated Demo is complete.

## 2. Authority and risk

Consumed authority is limited to the delivery-matrix AIO-A/B/C, SR-A/B/C and SS-A/B/C rows; D-039, D-044 and D-058; ACG Audio, Speech, Identity, Cancel, Capability and Error/Privacy rules; the AIO-B/X-WEB implementation review; and the adjacent Gateway/AIO/Speech code and tests.

Although the matrix labels the individual batch adapters Tier 1, this coherent implementation batch is treated as Tier 2 because it adds Gateway identity enforcement, server credential handling, timeout/cancel behavior, idempotency and stale-result fences. D-053 therefore applies. Agent, Tool, Task, history, turn commit, business cancel, audio presentation authority and raw-audio persistence are forbidden effects in this package.

## 3. Provider and credential decision proposal

The dependency-injected formal Adapter supports an OpenAI-compatible HTTP Provider:

- recognition: `POST {api_base}/audio/transcriptions`, multipart WAV plus configured model and requested language;
- synthesis: `POST {api_base}/audio/speech`, configured model/voice, server-authorized exact spoken text and `response_format=wav`;
- official endpoint/format references: [Speech to text](https://developers.openai.com/api/docs/guides/speech-to-text) and [Text to speech](https://developers.openai.com/api/docs/guides/text-to-speech);
- Provider-specific HTTP/request/response objects terminate inside the Adapter;
- Provider/model/voice are observable provenance, while endpoint and credential are not returned;
- responses are streamed into bounded memory and closed on success, HTTP failure, timeout or cancellation;
- non-loopback credentials require HTTPS and redirects are disabled.

Configuration is Gateway-process environment only:

- `LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED`
- `LIVE_VOICE_SPEECH_PROVIDER=openai-compatible`
- `LIVE_VOICE_SPEECH_API_BASE`
- `LIVE_VOICE_SPEECH_API_KEY`
- `LIVE_VOICE_SPEECH_STT_MODEL`
- `LIVE_VOICE_SPEECH_TTS_MODEL`
- `LIVE_VOICE_SPEECH_TTS_VOICE`

The default, disabled, incomplete, unknown-provider or insecure configuration creates an unavailable Provider and fails closed. A configured Provider alone is also unavailable to the formal route until a server-owned authorization resolver is injected. No fake Provider can become formal. The key is excluded from dataclass representation, capability output, browser RPC input/output and stable error messages. No machine credential was used in this Worker.

## 4. Package-local contract

Gateway methods:

- `live_voice.speech.capabilities`
- `live_voice.speech.recognize_batch`
- `live_voice.speech.synthesize_batch`
- `live_voice.speech.cancel`

The three mutating/long-running methods require `live-voice.contract.v2`, request/operation/correlation IDs, explicit `session_id`, exact subject/session scope and a bounded timeout. The Gateway injects query/header-derived subject identity only as `request_asserted`; it never upgrades that assertion to `authenticated`. Because the current repository has no trusted Web identity source, the default route fails `SPEECH_AUTHENTICATED_IDENTITY_REQUIRED` before the authorization resolver or Provider. Project scope is rejected because this package does not resolve project authority. All four methods are local-only and return before the Agent message callback, so their Agent/Tool/Task mutation count is zero.

Recognition accepts one finalized AIO-B capture as contiguous 20ms mono `pcm_f32` frames. The browser client creates a mono signed-16-bit PCM WAV without resampling; the server validates the exact RIFF/WAVE extent, declared sample rate, capture tuple and size before Provider invocation. A capture generation is an Adapter-instance token, not a cross-instance epoch: new unique capture IDs may restart at generation 1 after Adapter recreation, while exact capture-ID tombstones and active-tuple fences prevent reuse or late-result application. The result includes exact capture/track identity, final hypothesis, locale/timing, formal Provider/model provenance and `commits_turn=false`.

`authoritative_agent_text=true` is retained only as a browser request declaration; it is never accepted as authority. Before synthesis Provider invocation, a server-owned resolver must return an immutable binding exactly matching authenticated subject/scope, operation/operation ID, correlation, response tuple, unit and a SHA-256 digest over the display/spoken text, transforms, locale, voice and output rate. Recognition uses the same seam bound to exact subject/scope, operation/correlation, capture tuple and raw-audio/request digest. A missing, denying, failing or non-exact resolver produces a stable unavailable/permission failure with zero Provider effect.

After authorization, synthesis requires the exact response tuple/unit, display/spoken render plan, locale, optional voice and actual required AIO-B playout rate. Provider output must be a non-empty bounded mono signed-16-bit PCM WAV at that exact rate. The client rejects mismatch instead of silently resampling, converts PCM16 into exact-rate Float32 20ms chunks and retains formal provenance. It does not enqueue, play or claim presentation itself.

Operation IDs are idempotent only for byte-equivalent logical input; conflicting reuse is rejected. Exact capture identities and response tuples fence stale/duplicate results. Operation replay and identity tombstones are explicitly bounded and declared through capability limits; operation-local Speech Ports do not retain completed audio/session state. A newer client operation locally fences the prior result and attempts scoped cancellation.

Timeout, exact cancel and close use a first-terminal fence on the exact scope/operation. Deadline expiry returns a terminal `TIMEOUT` without awaiting Provider cancellation cooperation. The Provider worker is strongly retained, its terminal exception is consumed, and it continues to occupy bounded operation capacity until actually closed. Late completion updates only truthful completion/cleanup accounting and cannot recreate transcript, Speech event, audio or success. `close(timeout_ms)` is retained and shielded from caller cancellation, has a 10–5000 ms hard wait bound, and reports counts plus exact operation IDs for unresolved Provider/operation stragglers instead of claiming clean shutdown.

## 5. Scenario oracle

| ID | Scenario | Required result | Forbidden effect |
|---|---|---|---|
| P-01 | finalized contiguous AIO-B capture, available formal Provider | final text with exact capture and formal Provider/model provenance | TurnCommit, Agent/Tool/Task/history mutation |
| P-02 | authoritative Agent render plan, exact Provider/AIO rate | WAV maps to ordered AIO-B chunks with formal Provider/model/voice provenance | playback or presented claim before AIO ACK |
| N-01 | query/header-only identity, absent authenticated principal, authenticated but unauthorized subject or unresolved project | stable missing-authentication/authorization denial before Provider | Provider request, external cost or other-scope mutation |
| N-02 | partial capture, malformed/gapped/oversized audio, false browser authority declaration or malformed Provider response | stable closed-contract failure | fake/empty success or audio application |
| N-03 | forged `authoritative_agent_text=true`, or scope/correlation/response/unit/render-text digest differs from server grant | stable permission failure before Provider | TTS request, audio or Speech event |
| F-01 | local flag off, incomplete/insecure Provider config or Provider unavailable | formal capability unavailable; explicit Browser fallback identity remains | Gateway/Provider request or automatic hidden fallback |
| T-01 | Provider propagates, swallows once or continuously swallows cancellation | RPC returns terminal timeout/cancel within its hard bound; retained straggler holds bounded capacity and close reports it | result/event/audio resurrection, orphan task or false completion |
| S-01 | duplicate/conflicting operation, reused capture ID or stale response | replay exact operation or reject before a second Provider invocation/application | duplicate Provider call or duplicate application |
| R-01 | existing Browser Speech and AIO adapters | existing focused suites remain green | product-route rewrite or fallback provenance loss |
| C-01 | newer capture/response completes before prior Provider call | prior late result becomes `null`/inapplicable | stale text/chunk application |
| K-01 | secret/endpoint and raw audio inspection | secret/endpoint absent from capability/browser bundle and stable errors; raw audio memory-only | browser credential, log/error secret or persistence |

## 6. Integration seam, blocker and proposals

The formal Gateway route is **BLOCKED** on this repository state. The minimum Integration Owner interface is:

1. a trusted Web/middleware principal resolver that creates `Assurance.AUTHENTICATED` only from an authenticated server session and never from query/header `user_id`;
2. a server-owned `SpeechAuthorizationResolver` (or accepted equivalent) that compares the requested immutable `SpeechAuthorizationBinding` with authoritative Agent response/render state and returns the exact binding only for an authorized external Provider invocation;
3. a composition seam that binds the resolver to the exact authenticated session and keeps denial/unavailability fail-closed before raw audio, text, credentials or external cost cross the Provider boundary.

No such production source is present in this Worker’s routed code. This candidate does not invent one. The browser boolean remains a declaration and the current Gateway-created `request_asserted` context is deliberately denied.

The Integration Owner can inject a `webClient.request`-signature-compatible transport and compose formal-versus-Browser selection later. The transport must explicitly suppress/redact raw Speech params: the existing development Web traffic logger records ordinary request objects, so directly binding the current `webClient.request` in a development build would violate the raw-audio memory-only boundary. Product composition therefore requires either a non-logging Speech transport or an Integration-Owner-approved sensitive-request/redaction extension. This Worker does not change that shared logger, `useLiveVoiceDemo` or the final Web route.

Cross-package decisions remain proposals rather than silently widened ownership:

1. The current candidate wire format is bounded base64 `wav_pcm16_mono` over existing Web RPC. X-E2E/X-WEB should confirm whether this stays the Alpha codec or moves to a binary transport; the Provider Adapter contract should remain batch WAV either way.
2. D-058 forbids hidden custom resampling here. Therefore SS-B fails `SPEECH_SAMPLE_RATE_MISMATCH` unless Provider WAV rate equals the unlocked AIO-B AudioContext rate. X-E2E/X-WEB must explicitly choose whether a future audited resampler belongs server-side, in a transport/media package, or not at all. This package does not claim the common 24 kHz Provider output can directly play through a typical 48 kHz browser context.
3. X-WEB must approve a sensitive-request/redaction seam before the package client is bound to the shared development traffic logger; raw base64 audio must never enter `/__dev/ws-log`.

## 7. Review and evidence ledger

| Pass | State | Findings/fixes/evidence |
|---|---|---|
| Integration review remediation | `READY FOR APPROVAL; UNCOMMITTED` | Review of preserved candidate `cea69737` found that `asyncio.wait_for` could wait for and accept a Provider that swallowed cancellation, and that request-asserted identity/browser authority declarations could reach credentialed Providers. The uncommitted repair adds absolute first-terminal fencing, retained bounded stragglers, bounded shielded close, authenticated identity enforcement and exact server authorization bindings. Adversarial tests cover one-time/continuous cancellation swallowing, cancellation converted to success, completion after the absolute deadline but before timer dispatch, timeout/cancel/close, success/error-before-cancel ordering, no late transcript/event/audio resurrection, bounded capacity, forged Web identity, absent/denied authorization and every requested synthesis binding mismatch. |
| Preserved-candidate implementation self-review | `HISTORICAL PASS AFTER FIXES` | Before `cea69737`, complete source/test review found that the existing before-callback mechanism still continued into the Agent callback; added a Speech-only local-handler terminal set plus a raw Web request test proving callback count zero, without changing `chat.send`. It also fixed reservation/capacity ordering, bounded Provider response buffering, recognition cancel cleanup, Provider-output error classification, API-key representation, oversized base64 precheck, exact RIFF extent validation, structural response identity and capability operation mapping. This row does not review the remediation diff. |
| Preserved-candidate cold complete-diff review | `HISTORICAL PASS AFTER FIXES` | Before `cea69737`, the cold pass removed an accidental whole-file formatting expansion and fixed cross-scope correlation/fingerprint fencing, AIO capture lifecycle semantics, bounded state and Provider-completion evidence. This row does not review the remediation diff. |
| Preserved-candidate independent review | `HISTORICAL PASS AFTER FIXES` | Before `cea69737`, `/root/independent_review` found AIO token mismatch, unbounded retained state, terminal-cancel overclaim and missing Adapter-recreation evidence. Those candidate findings were fixed. This row does not review the remediation diff. |
| Remediation implementation self-review | `PASS AFTER FIXES` | Reviewed the timeout/cancel/close state machine, Provider task ownership, capability truth, authorization ordering, exact binding and zero-effect tests. It added explicit close straggler IDs, synthesis late-audio/event coverage, post-close unavailable capability/new-operation rejection, an event-loop atomic deadline callback, and truthful authority wording. The later cold/independent deadline finding was then fixed with `deadline_at` plus one unified worker/fence first-terminal transition. |
| Remediation cold complete-diff review | `PASS AFTER FIXES` | Re-read the complete uncommitted diff against the integration findings, Task Packet, root `AGENTS.md`, ACG identity/authorization boundary, existing Gateway/Speech behavior and actual tests. It found that `asyncio.wait(..., timeout=...)` could observe a just-late done worker and that closed capability stayed available; both were fixed. After the independent absolute-deadline semantic fix and the final error-before-cancel test, a repeated complete-diff cold review found no remaining actionable item. |
| Remediation independent review equivalent | `PASS AFTER FIXES` | Native `/review` remained unavailable: exact probe `codex review --help` failed with Windows `Access is denied`. The exact substitute was the separate read-only agent `/root/independent_review` over the complete remediation diff. Its first pass found that an overdue timer could be cancelled by a Provider monopolizing the event loop and that the ledger reused historical evidence; its second pass requested explicit Provider-error-before-cancel evidence. The implementation adopted an absolute deadline/worker terminal and the missing adversarial test. Its final pass reported no remaining code/test finding. Limitation: the independent pass did not execute tests, a real Provider, browser or audio device. |
| Automated verification | `PASS WITH TOOLING LIMITATION` | Remediation-focused Python: 35/35. Final affected Python Gateway/ACG/Speech/identity/Web-handler regressions: 171/171 (`-W ignore::SyntaxWarning` only bypasses a Python-3.12 invalid escape in third-party `pysbd`). Three critical deadline/cancel race tests passed three consecutive runs (9/9). Strict target TypeScript + esbuild + Node package tests: 8/8. Existing Browser AIO/Speech/TTS regressions: 58/58 (39 + 7 + 2 + 10), using the already-installed dependency cache from the main worktree because this independent worktree has no local `node_modules`. `ruff check`, format, compile and final diff checks passed. Repository ESLint has no discoverable configuration, so no ESLint pass is claimed. |
| Real Provider/device evidence | `NOT RUN` | No machine credential, external Provider or real microphone/playout service was used. Integration must record configured Provider/model/voice, exact rates, environment and observable safe evidence before any real-service or release claim. |

## 8. Explicit exclusions

- SR-C/SS-C streaming, RM-B/C, CR/AB/P3 authority and any final product composition;
- `useLiveVoiceDemo`, the current integrated fallback route, ACG/schema changes, shared STATUS/README/decisions/roadmap/validation files and final Replacement Ledger;
- resampling, binary transport, deployment/proxy/CSP/CORS closure and real-service credentials/evidence;
- production authenticated identity and authorization source; the formal default Gateway route remains blocked/fail-closed until Integration Owner composition;
- formal TurnCommit/Agent dispatch, Tool/Task/history mutation, business cancellation or audio presentation authority;
- commit, push, merge, rebase or cherry-pick without their separate exact approval Gates.
