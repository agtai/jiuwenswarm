# Live Voice product composition Gate 0

> Frozen: 2026-08-06
>
> Contract: `live-voice.product-composition.gate0.v1`
>
> Role: stable product-composition interface and ownership packet. Mutable progress remains owned by `STATUS.md`.

## 1. Gate result and truth boundary

Gate 0 freezes the seams required to compose the ten landed foundations and the next bounded packages without treating source integration, registration, manifests, mocks, automated tests, or an activation function as a completed product route.

The current product route remains default-off. This packet does not register a Gateway handler, mount a new Web product entry, create a trusted identity, open a Provider or device, start an Agent/Task runtime, connect an exporter, or grant Replacement Ledger credit.

The canonical route-truth contract is implemented as a pure Python/TypeScript boundary plus a language-neutral fixture. Existing Web-shell `unsupported` and `unknown` diagnostics remain intact in their package; the new product boundary maps both to `unavailable` and maps explicit flag-off to `disabled`.

## 2. Canonical composition interfaces

### 2.1 Trusted product authority

The server-owned authority package exposes:

```text
ProductAuthorityService.resolve(ProductAuthorityRequest) -> AuthorityDecision
AuthorityDecisionStatus = AUTHORIZED | DENIED | UNAVAILABLE
```

Only an `AUTHORIZED` decision carries one immutable `ResolvedProductAuthority`. Route, header, query, client metadata, `ScopeRef`, and `ContextRef` claims are comparison inputs only. They never grant identity, scope, capability, operation, resource, correlation, or confirmation authority.

The trusted resolver lookup contains only server-owned session plus exact operation, capabilities, correlation, and resource identity. Zero candidates are absent; multiple candidates are ambiguous. Feature-off or an absent/failing resolver is `UNAVAILABLE` with no resolver or downstream effect.

Package-owned narrow adapters are:

- `SpeechAuthorityResolverAdapter.authorize(SpeechAuthorizationBinding) -> same binding | None`; `UNAVAILABLE` uses a constant safe exception that the existing formal Speech service already maps fail-closed.
- `P2AuthorityAdapter.bind(...) -> P2AuthenticatedContext | None`; this happens before Agent/Harness/runtime allocation and returns the exact authenticated authority and scope without constructing P2.
- `P3AuthorityAdapter.resolve(...) -> P3AuthorityContext | None`, followed by `to_task_grant(...)`; queries need no confirmation, while mutations require an exact trusted confirmation and the existing durable verifier. The authority Adapter never consumes confirmation itself.

No safe representation may contain raw claims, credentials, resolver state, tokens, endpoint data, or arbitrary metadata.

### 2.2 P1 Speech and Media

Formal batch Speech continues to consume the exact existing `SpeechAuthorizationBinding`. The Browser/Gateway media package exposes side-effect-free factories equivalent to:

```text
create_gateway_media_activation(MediaActivationRequest, *, on_audio_frame)
createBrowserGatewayMediaActivation(request)
```

An active result requires an already server-authored immutable `MediaAuthorityBinding`. It binds authority evidence, authenticated Session, connection and epoch, media session, interaction, track, correlation, direction, exact capture-or-response generation, actual rate, and exact 20 ms mono `pcm_f32` format. Downlink also binds the exact response, response generation, and unit.

Attach, ACK, detach, pressure, close, and playback-stop receipt are typed semantic objects inside product code. Raw bytes exist only at the `live-voice.media.v1` codec/transport boundary. Binary audio begins with the closed `LVM1` header and carries no arbitrary JSON or identity assertion. An exact semantic attach must be accepted before binary audio.

The dedicated same-origin binary WebSocket handler and registration remain Integration-Owner files. They must not use the current JSON WebSocket logger, and they remain disabled until trusted binding, non-logging transport, AIO capture/playout hooks, generation replacement, and cleanup are all present. A read-only pre-integration audit found that injecting the current `webClient.request` into `GatewayBatchSpeechClient` can persist `audio.data_base64` to `ws-dev.log` in Vite DEV because that logger does not redact the field. Until a real transport/logger test proves zero audio-payload persistence, the route reason is `MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN`; package transport tests are not that evidence.

### 2.3 P2 Agent and Interaction

The composition owner constructs `AgentConversationRuntime` only after `P2AuthorityAdapter.bind` succeeds. The runtime continues to consume one committed `TurnCommit`, the D-059 Harness reservation/round authority, CR-selected context, exact response/round/correlation identity, PresentationAck, presented-history selection, and its retained shutdown result.

The product Adapter boundary is:

```text
activate authorized exact interaction -> retained P2 activation lease
submit committed TurnCommit -> AgentConversationHandle
apply exact PresentationAck -> PresentationAckResult
close/detach -> retained bounded shutdown truth
```

An Interaction Engine package may return typed observation/intention values to this boundary, but it owns no Agent, Tool, Task, history, presentation, or cancellation side effect. `playback.stop`, `response.cancel`, `round.cancel`, and `task.cancel` remain four separate exact scopes; an Interaction intent cannot upgrade one into another.

A pre-integration audit also found that `AgentConversationRuntime` can block authoritative terminal consumption and bounded close when `notification_capacity=1` and the UI notification consumer is absent or slow: `_publish()` awaits `Queue.put()` on the same sequential consumer path. Until an owner fix proves bounded terminal consumption/close under full-queue and slow/no-consumer conditions, P2 reports `P2_NOTIFICATION_BACKPRESSURE_UNRESOLVED`. The next bounded pre-II package owns that regression and fix; Gate 0 does not modify the runtime here.

### 2.4 P3 query, control, and progress return

P3 query and mutation are separate product capabilities:

- Query uses trusted authority and the current formal `task.get/list/status/events` composition without confirmation.
- Mutation uses trusted authority plus exact confirmation issuance and the existing durable confirmation verifier. Without a trusted issuer, create/cancel remain unavailable.
- Progress return consumes an already-authorized exact-task event source, exact origin generation, foreground facts, a notification arbiter, and typed voice/text sinks. It never calls TTS, writes Chat/history, changes Task lifecycle, or emits business cancellation.

The current TaskEvent/progress foundations cannot prove the positive voice route. `TaskEventSubscription` starts after the current Store head and omits the authoritative prefix. The Store sequence also legitimately interleaves `attempt.*` and control events, while `ProgressNotificationArbiter` requires contiguous source and progress streams beginning at sequence zero. Reading then attaching is racy; filtering or resequencing would falsify source truth.

The required future owner seam is an authority-backed atomic TaskEvent snapshot/cursor lease plus arbiter ingestion that consumes every canonical source event and records either its exact projection or a verified no-projection advance. Until that shared API exists and proves a no-gap/no-duplicate handoff, voice progress reports `TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE`. A package-only prepared-stream test double is contract evidence, not product activation evidence.

An independently truthful text/UI projection may carry the raw canonical TaskEvent identity, sequence, producer, known lifecycle state, and outcome. It must not invent percent, summary, urgency, speakability, artifacts, blocking questions, completion text, or error detail.

### 2.5 Browser audio

`BrowserAudioIOAdapter` remains the browser device and render owner. Construction and capability inspection are side-effect-free. Capture begins only on explicit activation and produces exact `CapturedAudioFrame` values. Downlink reaches playout only after exact current response/generation/unit validation. Browser local stop returns the existing exact receipt and never implies response, round, or task cancellation. Render completion is not proof that a person heard audio.

### 2.6 Observability

X-OBS consumes already-authoritative public facts after business acceptance. Collectors and `LiveVoiceObservabilityExporterBuffer` never become identity, lifecycle, cancellation, presentation, or success authority. Export is bounded, explicitly started, and diagnostic-only; exporter failure/backpressure cannot rewrite or block a business result. No transcript, raw audio, credential, device identity, arbitrary label, URL, or unreviewed content crosses the evidence seam.

## 3. Product route truth

| Truth             | Exact meaning                                                                                                      | Required core reason/evidence                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `formal`          | Trusted authority resolved, the exact formal activation lease is open, the runtime path was observed, and any stop owned by that segment has affirmative closure evidence | `FORMAL_ROUTE_OBSERVED`; generic `TRUSTED_AUTHORITY_RESOLVED`, `FORMAL_ACTIVATION_LEASE_OPEN`, `RUNTIME_PATH_OBSERVED`; segment-specific closure below |
| `fallback`        | An explicit retained compatibility fallback is selected                                                            | `EXPLICIT_FALLBACK_ACTIVE`; `FALLBACK_ROUTE_SELECTED`                                                          |
| `demo_substitute` | A D-047-frozen Demo/Compatibility substitute is selected and remains non-formal                                    | `D047_DEMO_SUBSTITUTE_ACTIVE`; `D047_LEGACY_ROUTE_SELECTED`                                                    |
| `unavailable`     | The requested path cannot safely activate, lacks authority/hooks/evidence, or failed before trustworthy activation | one closed unavailable reason and bounded evidence identifiers                                                 |
| `disabled`        | The owning product flag is off and the path has zero allocations/calls/effects                                     | `FEATURE_DISABLED`; `FEATURE_FLAG_OFF`                                                                         |

The complete closed Gate-0 segment, reason, and evidence vocabularies are shared through `tests/fixtures/live_voice_product_composition_gate0_v1/contract.json`. `formal_seams`, `manifest_only`, file presence, package tests, route registration, mocks, or configured Provider values do not satisfy the `formal` evidence set. A dependent segment cannot be `formal` unless the authority segment is also `formal`. Any formal fact carrying `P2_NOTIFICATION_QUEUE_BLOCKING_RISK` or `DEV_AUDIO_LOG_PERSISTENCE_RISK` is contradictory. In addition to the three generic proofs, `p1.speech_media` requires `MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED`, and `p2.agent_interaction` requires `P2_NOTIFICATION_BACKPRESSURE_CLOSED`; authority, P3, browser-audio and observability facts do not inherit unrelated stop proofs. These identifiers are contract prerequisites only: this Gate-0 batch supplies neither closure and claims no runtime evidence.

## 4. Shared-file ownership and conflict rules

| Owner                        | Exclusive files/surfaces                                                                                                                                                                                                                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Integration Owner            | product-composition contract/root; central Gateway and Web registrations; dedicated binary WebSocket route; shared feature flags; `integratedWebRouteShell.ts`; product panel/mounts/locales; cumulative tests; route diagnostics; shared fixtures; README/review records; final STATUS reconciliation |
| Trusted Authority worker     | new `product_authority.py` and direct tests only                                                                                                                                                                                                                                                       |
| Speech/Media worker          | new package-local Browser/Gateway transport files, direct tests, and its isolated vector fixture only                                                                                                                                                                                                  |
| VB-C worker                  | new `task_progress_return.py`, direct tests, and at most one package-local integration test only                                                                                                                                                                                                       |
| Later II/X-OBS/X-WEB workers | new non-overlapping package files and direct tests; shared entrypoints remain IO-owned                                                                                                                                                                                                                 |

Rules:

1. Workers do not edit `__init__` exports, Gateway/Web registrations, package scripts, shared schemas, feature flags, UI mounts, locales, roadmap/status/review files, or another foundation.
2. A required shared change is returned as a hook request. The IO either owns it in a later reviewed batch or keeps the route unavailable.
3. Interface changes after this freeze require an explicit Gate-0 amendment and affected review; an implementation summary cannot silently redefine the contract.
4. The inherited user-owned `STATUS.md` modification is excluded from every functional diff and commit packet until final IO documentation reconciliation.
5. D-047 authorities remain frozen: `useLiveVoiceDemo`, frontend TaskBridge, legacy `schedule.*`, and JSON state stay fallback/substitute/carrier surfaces and receive no new formal authority.

## 5. Feature flags and zero-side-effect contract

The existing frontend root flag remains `VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB`, default off. IO wiring will also own default-off server/product flags for product composition, realtime media, and Task progress return; package constructors still receive explicit booleans and do not read environment state themselves.

When the owning flag is off, evaluation returns before Adapter facts and creates or invokes none of the following:

- authority resolver, Provider, endpoint, credential, network route, socket, or binary send;
- microphone permission request, `MediaStream`, `AudioContext`, AudioWorklet, playback source, or timer;
- Agent/Harness/runtime, Tool, Task command/query, Store/outbox mutation, subscription, queue, worker, reconciliation, or cancellation;
- Chat/history mutation, PresentationAck, TTS, notification intent, collector record, exporter worker, or external telemetry sink.

The existing text route, Browser Speech/TTS fallback, Demo substitute, and committed-only input rules remain behaviorally unchanged. Formal failure never triggers a hidden fallback after a partial formal effect; route selection is explicit before activation.

## 6. Integration order

Every Git operation remains separately user-approved. After approved worker commits exist, the IO reviews and proposes one integration operation at a time in this order:

1. trusted product authority;
2. Speech/Media package source integration, still unavailable at product level;
3. VB-C progress-return package, with voice progress still unavailable;
4. bounded P2 notification-backpressure regression and owner fix;
5. IO authority/registration/route-diagnostic composition and cumulative smoke, with media logging still blocked pending zero-persistence evidence;
6. Interaction Engine/Realtime Media composition after its contract is stable;
7. X-OBS consumer/export wiring;
8. X-WEB controls and presentation wiring;
9. secure-origin, real Provider/device/service, restart/recovery, and immutable Gate evidence.

No earlier step is relabelled formal because a later dependency is planned.

## 7. Cumulative smoke matrix

| Step                         | Positive assertion                                                                                          | Negative/fail-closed assertion                                                                                                      | Expected route truth                                                                                         |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Gate-0 skeleton              | Python/TypeScript vocabularies match; explicit fallback and D-047 substitute remain distinct                | flag-off does not inspect route facts; manifest-only formal maps unavailable                                                        | all segments `disabled` off; current retained paths `fallback`/`demo_substitute`; formal seams `unavailable` |
| + Authority                  | exact trusted candidate resolves once and narrows operation/capabilities                                    | absent, ambiguous, expired, cross-scope/correlation/resource/confirmation claims have zero downstream effects and safe presentation | authority may become formal only after real activation evidence; dependent segments remain unavailable       |
| + Media package              | exact attach/binary/ACK/detach round trip passes package tests                                              | wrong binding/generation/sequence/cursor/format/pressure detaches with zero frame callback; off opens nothing; real DEV logger test proves zero audio persistence | P1 remains unavailable until IO binary route, trusted binding, AIO/Provider hooks and zero-persistence evidence exist |
| + VB-C package               | exact origin/generation and truthful text projection pass package tests                                     | real voice activation returns `TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE` with zero subscription/sink/business effects            | P3 progress voice unavailable; text remains package evidence until IO registration                           |
| + IO composition             | one persisted Session/correlation is carried through selected adapters and cleanup is retained              | partial activation rolls back; stale generation has zero Agent/Task/audio/history effect; flag-off preserves text/fallback; full notification queue cannot block terminal consumption or bounded close | only observed active paths may be formal after both audit stops are closed                                   |
| + II/Realtime                | committed final alone enters P2; exact four cancellation scopes remain separate                             | partial speech, stale media, wrong round/response, and transport loss cannot widen effects                                          | P2 formal only after real runtime-path observation                                                           |
| + X-OBS                      | accepted public facts share the exact correlation and export asynchronously                                 | exporter full/failure/timeout changes no business result and leaks no content                                                       | observability formal only when a real consumer/export path is observed; backend/SLO still separate           |
| + X-WEB and real environment | one bounded Chrome Session exercises microphone -> Speech -> Agent/Tool -> Task -> progress -> presentation | fallback, permission/device/provider/media/Agent/Executor faults, restart and cleanup remain truthful                               | route truth follows observed segment facts; Gate credit requires separate acceptance evidence                |

After every approved integration, rerun that package's focused checks, the accumulated Gate-0 smoke, affected Live Voice regressions, flag-off checks, and the relevant build/static checks. Tier 2/3 semantic changes repeat D-053 self-review, cold complete-diff review, and independent review or an exact recorded substitute/limitation.
