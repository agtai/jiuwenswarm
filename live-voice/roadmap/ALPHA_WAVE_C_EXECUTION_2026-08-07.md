# Live Voice Alpha Wave C execution packet

> Frozen: 2026-08-07
>
> Source baseline: pushed `hx/0803_live_voice` commit `107104bb22b9cfc705b02634a4eaf86d1d64f3bf`
>
> Integration branch: local `codex/lv-alpha-wave-c-integration`; remote updates prohibited
>
> Authority: D-046, D-053, D-060, D-061, [Alpha parallel execution](ALPHA_PARALLEL_EXECUTION_2026-08-06.md) and [Product composition Gate 0](PRODUCT_COMPOSITION_GATE_0_2026-08-06.md)
>
> Role: stable dependency, ownership, oracle, review and recovery contract. Mutable progress, candidate HEAD, environment facts, blockers and Gate state remain exclusively in [STATUS](../STATUS.md); final results belong in a later frozen integration review.

## 1. Outcome and truth boundary

Wave C advances every implementation and acceptance slice supported by real repository and machine dependencies. One unavailable Provider, device, deployment, Executor or observability backend does not pause unrelated work. A missing external condition leaves only its dependent segment `UNAVAILABLE`, `BLOCKED` or `NO_CHANGE`; no Session creates a fake product Provider, exporter, deployment, Executor or real-E2E claim.

The batch targets one clean, reviewed, locally integrated and unpushed candidate. It does not predeclare the Integrated Demo runnable, Web Alpha accepted, production readiness or Replacement Ledger credit. Package hardening, source integration, central registration, observed real path and Gate evidence remain distinct facts.

The fixed input is the pushed Wave A+B documentation baseline above. Its tested implementation and evidence remain in the [Wave A+B integration review](../ALPHA_WAVE_AB_INTEGRATION_REVIEW_2026-08-07.md); this packet does not restate or mutate that review.

## 2. Sessions, branches and single-writer rule

| Role | Local branch | Persistent ownership |
|---|---|---|
| Main Integration/Review | `codex/lv-alpha-wave-c-integration` | shared Authority/Composition, central registry and route order, Gateway/AgentServer/shared wire dispatch, stock-Web top-level ownership, integration history, cumulative verification, real candidate, documentation and evidence |
| T1 P1 Speech/Media | `codex/lv-alpha-wave-c-t1-p1` | browser Audio/Media leaves, server realtime-media leaves and selected Speech Provider leaves only after a real Provider decision/configuration exists |
| T2 P2 Runtime/Interaction | `codex/lv-alpha-wave-c-t2-p2` | CR/II/AB/Agent-Harness runtime leaves, exact presentation/history leaves and their focused tests |
| T3 P3alpha Task/Executor | `codex/lv-alpha-wave-c-t3-p3` | formal Task Core/Store/Executor, confirmation/voice-policy/progress leaves and their focused tests |
| T4 X-OBS/X-WEB/X-E2E | `codex/lv-alpha-wave-c-t4-x` | observability/exporter, leaf Web diagnostics and fault/E2E harnesses |
| Independent Reviewer | no writer branch | read-only task, Main and final combined review |
| Environment/E2E Preflight | no writer branch | read-only machine/dependency audit and real-Gate preparation; never reads or reports secrets |

Every implementation branch starts from the same reviewed governance commit created from the fixed source baseline. Only Main writes the integration worktree. Task Sessions never push and never update a remote ref.

## 3. Main-only ownership

Without a temporary exact lease from Main, Task Sessions must not edit:

- `AGENTS.md`, Live Voice router/status/decisions/roadmaps/reviews/evidence, acceptance, showcase or runbook files;
- `product_composition_root.py`, `product_composition_registry.py`, Product Authority/shared composition contracts and their top-level tests;
- `agent_ws_server.py`, shared `message.py`, `app_web_handlers.py`, Gateway/AgentServer routing and shared wire dispatch;
- stock-Web top-level route/panel, `ChatPanel`, package manifests, feature flags and i18n catalogs;
- Provider/Media/P2/P3/X-OBS central registration order, shared integration glue, cumulative smoke, real E2E candidate and Gate evidence.

Main may add only bounded shared hooks and integration glue. A large leaf state-machine change returns to its owning Task. Shared authority, protocol, route truth, lifecycle, cleanup, correlation, generation, binding or security conflicts are never guessed during integration.

## 4. Lane ownership and real-dependency release

### T1 P1 Speech/Media

Owned leaves and adjacent focused tests are:

- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/audioPort.ts`;
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts`;
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js`;
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserGatewayMediaTransport.ts`;
- `jiuwenswarm/server/live_voice/realtime_media.py`;
- only after an accepted real Provider/configuration decision: `jiuwenswarm/server/live_voice/speech_ports.py`, `jiuwenswarm/server/live_voice/batch_speech.py`, dedicated Provider leaves, `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechRecognitionAdapter.ts`, `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserSpeechSynthesisAdapter.ts` and `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts`;
- tests directly adjacent to the owned leaves.

The lane must first freeze actual transport, codec, sample rate, frame provenance and Provider batch/stream/cancel/STT/TTS capability. Before Main may register Media it must prove feature-off zero allocation/device/network/registration, denied/unavailable zero Provider calls, exact scope/correlation/generation/track binding, partial-start rollback and idempotent stop/close. Raw audio must never enter logs, persistence, URLs, history or error payloads, and the registered product route must pass a route-to-disk zero-persistence regression. When real desktop-Chrome conditions exist, exercise capture, playout, exact-response stop, permission revoke, device loss, autoplay, background/resume and reconnect. No Provider or physical device means the product registry remains unavailable.

### T2 P2 Runtime/Interaction

Owned leaves and focused tests are:

- `jiuwenswarm/server/live_voice/interaction_engine.py`;
- `jiuwenswarm/server/live_voice/conversation_runtime.py` and `jiuwenswarm/server/live_voice/conversation_runtime_loop.py`;
- `jiuwenswarm/server/live_voice/agent_bridge.py`, `jiuwenswarm/server/live_voice/agent_bridge_runtime.py` and `jiuwenswarm/server/live_voice/agent_conversation_runtime.py`;
- `jiuwenswarm/server/live_voice/jiuwenswarm_agent_adapter.py` and `jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py`;
- `jiuwenswarm/server/live_voice/formal_history_writer.py`, `jiuwenswarm/server/live_voice/presentation_ledger.py` and `jiuwenswarm/server/live_voice/progress_notification_arbiter.py`;
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/conversationRuntimeReplica.ts`;
- tests directly adjacent to the owned leaves.

The lane preserves D-059 committed-only input, two-phase admission, exact round authority/cancel, response/generation fencing, presented-only history and retained shutdown. Partial speech causes zero Agent, Tool or history effect. It must cover VAD/EOT/working notice, barge-in, stop, revise and delegate while keeping playback, response, round and task cancellation distinct. Audio PresentationAck is browser-render truth, not proof that a person heard audio; UI text history accepts only the acknowledged contiguous presented prefix. Disconnect/reconnect, response loss, late result, cancel races and retained cleanup stay exact, and background tasks must not freeze microphone capture, new Turns or foreground answers. It may connect real voice only after T1 provides a real Media dependency. Without Media it still verifies the real committed-text Agent/Tool environment and fault-hook gaps, but it cannot claim voice closure. Session-current cancellation is never relabelled exact cancellation, and the 256-turn runtime limit remains unchanged unless a separate owner/design/review is accepted.

### T3 P3alpha Task/Executor

Owned leaves and focused tests are:

- `jiuwenswarm/server/live_voice/formal_task_models.py`, `jiuwenswarm/server/live_voice/task_core.py`, `jiuwenswarm/server/live_voice/persistent_task_core.py` and `jiuwenswarm/server/live_voice/task_store.py`;
- `jiuwenswarm/server/live_voice/executor_port.py` and `jiuwenswarm/server/live_voice/project_code_executor.py`;
- `jiuwenswarm/server/live_voice/p3_confirmation.py`, `jiuwenswarm/server/live_voice/voice_task_bridge.py`, `jiuwenswarm/server/live_voice/voice_task_policy.py`, `jiuwenswarm/server/live_voice/task_event_subscription.py` and `jiuwenswarm/server/live_voice/task_progress_return.py`;
- new package-local Web task-control leaves that do not touch Main-owned entrypoints;
- tests directly adjacent to the owned leaves.

The lane preserves authenticated query, confirmation-before-mutation, exact task/command/attempt/project/principal/scope/binding, durable outbox/reconciliation and idempotent conflict behavior. It must validate formal `create/get/list/status/cancel/events`, zero mutation before confirmation and exact mutation after confirmation, duplicate/conflict/replay, mutation-unknown and reconciliation, task survival after disconnect and exact explicit task cancellation. TaskEvent must project to WorkProgress and return to the exact origin surface. Restart, duplicate/gap/reorder, concurrent-task and terminal recovery must remain truthful. A real mutation journey requires a disposable registered Code project, real model/configuration and Executor. Formal voice additionally requires an atomic TaskEvent snapshot/cursor and CR/Media authority handoff. Absent dependencies keep mutation or voice unavailable. Legacy `schedule.*`, TaskBridge and JSON state never become formal authority. Workspace support paths including `.gitignore`, `coding_memory/`, `prompt_attachment/` and `.agent_history/` must be relocated or governed explicitly rather than silently ignored.

### T4 X-OBS/X-WEB/X-E2E

Owned leaves and focused tests are:

- `jiuwenswarm/server/live_voice/observability.py`, `jiuwenswarm/server/live_voice/observability_exporter.py` and `jiuwenswarm/server/live_voice/product_observability_adapter.py`;
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/liveVoiceObservability.ts` and `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/webPlatformDiagnostics.ts`;
- new leaf diagnostics and fault/E2E harnesses that do not edit Main-owned entrypoints;
- tests directly adjacent to the owned leaves.

Product Gate 0 keeps `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/integratedWebRouteShell.ts` Main-exclusive in Wave C. T4 may inspect it and request one exact temporary lease, but has no default write ownership; any granted lease names the file, semantic scope and return point, and Main re-reviews the resulting shared route-truth diff.

The lane may implement a real sink/transport only when an exporter/backend contract and configuration exist. It must define retention, redaction, queue/backpressure, timeout, retry, shutdown and SLO facts; absent backend means no X-OBS registration. It must cover route, latency, queue, cancel, fence and task metrics plus P1/P2/P3alpha vertical and joint-journey fault/evidence harnesses. Deployment diagnostics cover HTTPS/WSS, reverse proxy, origin, CSP, CORS and WebSocket routing without moving Provider/model credentials into the browser. Deterministic in-memory fault harnesses remain test evidence, not an observability backend or deployed Gate; absent real deployment yields only verified configuration/diagnostic boundaries.

## 5. Required pre-implementation oracle

Before editing, each Task returns to Main:

1. exact owned files and any adjacent Main-only hook request;
2. positive business journey and authority owner for every accepted effect;
3. owner identity, scope, correlation, generation and track/round/task/attempt/confirmation binding;
4. state transitions, terminal truth and ACK-versus-completion behavior;
5. feature-off forbidden allocations, registrations, calls, writes and external effects;
6. denied/unavailable behavior and zero downstream effects;
7. correlation/generation/binding mismatch behavior;
8. replay/idempotency/conflict behavior;
9. caller cancellation/timeout and retained cleanup ownership;
10. retry, tombstone and eviction bounds;
11. fallback/Demo/legacy non-regression;
12. focused positive, negative, flag-off and affected tests;
13. real dependencies used, exact unavailable hooks and physical conditions;
14. explicit non-goals and file exclusions.

Main confirms the oracle and freezes adjacent shared hooks before coding. A hook request never authorizes a Task to edit a Main-only file.

## 6. Environment preflight and external choice rules

The read-only preflight checks configuration entrypoints and presence—not secret values—for Speech Provider capabilities; Browser↔Gateway transport/codec/frame facts; desktop Chrome, secure origin, permission/device/autoplay/page lifecycle; Gateway/AgentServer proxy, CSP/CORS and HTTPS/WSS; ports, network and service startability; disposable project registration/model/configuration/Executor; and X-OBS backend/transport/retention/SLO. It identifies what can run immediately, what requires a code hook and what only the user can provide. For every real Gate it returns the exact command or procedure, required evidence and applicable fault matrix; when no truthful command exists, it reports the missing hook instead of writing a placeholder into the runbook.

Every result uses exactly one class:

- `AVAILABLE_AND_VERIFIED`
- `AVAILABLE_BUT_UNVERIFIED`
- `IMPLEMENTATION_HOOK_MISSING`
- `PRODUCT_DECISION_REQUIRED`
- `MACHINE_PRIVATE_INPUT_REQUIRED`
- `PHYSICAL_USER_ACTION_REQUIRED`
- `UNAVAILABLE`

Multiple incompatible Provider, transport, codec, resampling or backend choices produce a concise decision package; no Session chooses silently. Work not dependent on that choice continues.

Task outcomes use:

- `NO_CHANGE`: the owned code already satisfies every dependency-independent requirement or no valuable owned change exists; return checks and exact reason;
- `BLOCKED`: a required product decision or unavailable shared owner prevents safe implementation; return the smallest decision/hook and zero-effect boundary;
- `UNAVAILABLE`: a real external condition is absent; retain truthful registry/capability state and identify what would make it available;
- implementation candidate: only when owned source/test changes add real value without inventing an external dependency.

## 7. Review and handoff

Every coherent batch runs focused positive, negative, feature-off and affected regression checks, then implementation self-review and Main cold complete-diff review. Tier 2/3 also receives an independent `/review` or recorded equivalent. Findings return to the owner; fixes rerun affected checks; semantic fixes repeat the final complete-diff review.

Only after Main and the independent reviewer pass may a Task create its final local commit. The handoff manifest is:

```text
base_sha:
source_branch:
final_commit:
exact_files:
risk_tier:
real_dependencies_used:
test_commands_and_results:
self_review:
main_cold_review:
independent_review:
unavailable_hooks:
known_limits:
forbidden_effect_assertions:
real_evidence_generated:
gate_credit_claimed:
```

A `NO_CHANGE`, `BLOCKED` or `UNAVAILABLE` lane returns the same evidence fields that apply, with no manufactured commit.

## 8. Integration lease and failure recovery

Before each integration Main declares source branch, exact reviewed commit, target integration branch, merge/cherry-pick/rebase method, exact file scope and lease start/end. One integration worktree has one writer. Main records any integration glue separately and repeats affected D-053 review when shared semantics change.

D-061 runs one cumulative smoke after the full reviewed batch. It covers normal routes; denied/unavailable authority; scope/correlation/generation/binding mismatch; replay, timeout, cancel and cleanup; feature-off zero effects; fallback/Demo/legacy regressions; complete Live Voice backend and frontend selections; every new test; and the production build.

If cumulative smoke fails, preserve the failing HEAD, logs and environment; classify deterministic versus environment/flaky failure; create a diagnostic branch/worktree from the batch base; replay commits in dependency order to find the first failing prefix; return the finding to its owner; integrate the reviewed fix; then replay and verify every later commit from the fix point in dependency order before rerunning the complete smoke. Never use a destructive reset or weaken tests.

## 9. Real E2E and closure

Automated tests and real E2E are recorded separately. Only actually observed Provider, browser/device, Agent/Tool, Task/Executor, deployment and exporter/backend paths may receive real evidence or Gate credit. Complete every non-physical task before requesting one consolidated user action package with exact Chrome/origin, devices, permission/autoplay actions, Provider presence, disposable project/model, deployment/backend and expected observations.

Closure is honest in either form:

- real dependencies available: the same immutable candidate passes real P1, P2, P3alpha, joint P2/P3alpha, Web platform/degradation, X-OBS backend, automated verification and D-053 review before the Alpha Gate is evaluated;
- real dependencies unavailable: every dependency-independent implementation, review, test and integration is complete, missing segments remain fail-closed, blockers and user preparation are exact, and the ledger/Gate remain unchanged.

Both forms require a clean integration worktree, no unowned Task changes, final Main cold review, independent combined review, `hx/0803_live_voice` unchanged after the shared baseline, no pushed Task/integration branch and no remote-ref update.

## 10. Documentation closure

After the final candidate exists, Main updates only current facts in STATUS and creates one frozen Wave C integration review. README stays routing-only. Runbook gains only commands actually executed. Historical evidence is never rewritten.

Required documentation checks are `git diff --check`, all relative Markdown links under `live-voice/`, tracked duplicates under `docs/zh/live-voice/`, archive warnings and a code/tests/decisions/roadmap/STATUS contradiction review. No acceptance evidence means the Integrated Demo stays not runnable and the Replacement Ledger remains `0/100`.

## 11. Final report contract

The final Main report records all of the following, even when a lane returns `NO_CHANGE`, `BLOCKED` or `UNAVAILABLE`:

1. actual baseline, integration branch and final SHA;
2. every Task branch, final commit or no-change result, exact files and outcome;
3. Environment/E2E preflight classifications;
4. real paths actually connected and observed;
5. paths still unavailable and their exact dependencies;
6. Provider, transport, codec, sample-rate and capability facts;
7. Chrome, device, origin, proxy and deployment facts;
8. Executor, project, model and configuration facts;
9. X-OBS backend, transport, retention and SLO facts;
10. focused tests, cumulative smoke and production build;
11. implementation self-review, Main cold review and independent review;
12. forbidden-effect assertions;
13. sanitized real E2E evidence actually generated;
14. whether Replacement Ledger or Gate eligibility changed, with acceptance authority;
15. final Git status and exact range from `hx/0803_live_voice`;
16. recommended local integration method into `hx/0803_live_voice`;
17. an explicit statement that no Task/integration branch and no remote ref was pushed or otherwise updated.
