# Alpha Wave C integration review — 2026-08-07

> Frozen dependency preflight, implementation, review and verification record for tested local code `4d1672eabce1edba205fd069369c3ffe64392605`. Mutable route, Git and next-action facts belong only in [STATUS.md](STATUS.md).

## Candidate identity and integration method

Wave C started from pushed Wave A+B documentation baseline `107104bb22b9cfc705b02634a4eaf86d1d64f3bf`. Local `hx/0803_live_voice` and `origin/hx/0803_live_voice` were synchronized to that exact commit with `0/0` divergence before work began. Main created local branch `codex/lv-alpha-wave-c-integration`, committed the frozen execution packet as `f80946fb896388298841f9bed366335d90f23e3a`, and used one declared single-writer lease to cherry-pick the reviewed T3 commit as integration commit `4d1672eabce1edba205fd069369c3ffe64392605`.

No Task or integration branch was pushed and no remote ref was created, changed or deleted. `hx/0803_live_voice` remained at the shared baseline. The intended later local integration, if separately selected by the user, is a fast-forward of `hx/0803_live_voice` to the clean Wave C integration candidate; this review does not perform that operation.

| Role | Local branch | Source result | Integrated result | Exact code scope |
|---|---|---|---|---|
| Main governance/integration | `codex/lv-alpha-wave-c-integration` | execution packet `f80946fb` | `f80946fb`, then T3 cherry-pick `4d1672ea` | governance plus single-writer integration only |
| T1 P1 Speech/Media | `codex/lv-alpha-wave-c-t1-p1` | `NO_CHANGE / UNAVAILABLE`; clean at `f80946fb` | no code commit | no file changes |
| T2 P2 Runtime/Interaction | `codex/lv-alpha-wave-c-t2-p2` | `NO_CHANGE`; clean at `f80946fb` | no code commit | no file changes |
| T3 P3alpha Task/Executor | `codex/lv-alpha-wave-c-t3-p3` | reviewed `9249c61858a593e8428329bfb0bee134f62bf0c0` | cherry-picked as `4d1672ea` | `formal_task_models.py`, `task_store.py`, `task_event_subscription.py`, `task_progress_return.py` and three adjacent tests |
| T4 X-OBS/X-WEB/X-E2E | `codex/lv-alpha-wave-c-t4-x` | `NO_CHANGE / BLOCKED`; clean at `f80946fb` | no code commit | no file changes |

The exact integrated T3 paths are:

- `jiuwenswarm/server/live_voice/formal_task_models.py`;
- `jiuwenswarm/server/live_voice/task_store.py`;
- `jiuwenswarm/server/live_voice/task_event_subscription.py`;
- `jiuwenswarm/server/live_voice/task_progress_return.py`;
- `tests/unit_tests/live_voice/test_persistent_task_core.py`;
- `tests/unit_tests/live_voice/test_task_event_subscription.py`;
- `tests/unit_tests/live_voice/test_task_progress_return.py`.

## Actual implementation result

### T3 atomic TaskEvent authority foundation

The concrete SQLite Task store can now create one bounded atomic authority snapshot containing the authoritative task head and its exact durable event prefix. A formal Task progress source consumes that prefix and the live suffix under one exact authorization fingerprint, task/scope/correlation binding and cursor contract. The subscription passes `min(queue_capacity, validation_capacity)` to the store, and an oversized prefix fails before event-row selection, materialization, queue allocation or worker creation.

Formal voice acceptance requires the exact concrete source and exact concrete SQLite store. Reserved handoff labels, subclasses, package-test sources, divergent grants and expired grants cannot claim the formal route. Authorization is rechecked after dequeue and before text, voice, deferred drain or acknowledgement effects. A close intent issued while activation is blocked remains retained even when its waiter is cancelled.

This is an authority-safe package foundation, not product voice completion. Product composition does not construct or register the new source. The current T2 arbiter has no reviewed no-projection sequence ingestion, so skipped attempt/control events can leave a later projected task event fail-closed on a sequence gap. Real Conversation Runtime/Media voice handoff, formal Executor mutation and product registration remain unavailable.

### P1, P2 and X-OBS lane results

- P1 already contained the dependency-independent bounded Media/browser activation leaves. The configured Speech surface was OpenAI-compatible batch STT/TTS only, with no streaming Adapter. No trusted Speech authorization resolver, registered Media consumer, selected Provider deployment or route-to-disk zero-persistence evidence existed, so the product registry correctly remains unavailable.
- P2 already contained the committed-final-text path through the real AgentManager/Harness/Conversation Runtime and exact presentation/history ownership. Its focused software route required no owned change. No real browser/service Agent/Tool journey, Media/VAD/EOT/audio acknowledgement composition or runtime rollover design was available; the 256-turn bound remains.
- X-OBS already contained bounded in-memory lifecycle/fault foundations and Web diagnostics. No exporter/backend, retention/redaction policy, retry/timeout/shutdown/SLO contract, secure deployment owner or central registration condition existed, so X-OBS remains unregistered.

The formal P3 Executor journey also retains the existing workspace-policy blocker: shared Code Agent support paths `.gitignore`, `coding_memory/`, `prompt_attachment/` and `.agent_history/` must be relocated or explicitly governed before a clean-workspace Gate. Wave C did not choose that product policy or hide those paths.

Main added no speculative central glue. In particular it did not register Media, formal P3 voice or X-OBS without their missing authority and real-dependency proofs.

## Read-only environment and dependency preflight

The preflight observed Windows `10.0.26200.0`, desktop Chrome `150.0.7871.116`, Python `3.12.9`, Node `24.14.0`, npm `11.9.0` and uv `0.12.1`. The repository `.venv` and frontend dependencies were usable. Docker was unavailable and the relevant local service ports were not listening.

| Dependency area | Classification and observed fact |
|---|---|
| Media wire contract | `AVAILABLE_AND_VERIFIED` in source/tests: WebSocket binary `LVM1`, `pcm_f32le`, mono little-endian, 20 ms frames, actual 8–192 kHz sample rate divisible by 50, `samples = rate / 50`, no custom resampling |
| Browser AIO source | `AVAILABLE_AND_VERIFIED` in source/tests: `getUserMedia`, AudioWorklet capture/playout, exact lifecycle and stop ownership |
| Speech Provider/capability choice | `PRODUCT_DECISION_REQUIRED`: only a batch OpenAI-compatible STT/TTS Adapter is present; no Provider or batch-versus-streaming target is selected |
| Speech Provider configuration | `MACHINE_PRIVATE_INPUT_REQUIRED`: no Provider credentials, API base, models or related runtime configuration is present |
| Registered Media route | `IMPLEMENTATION_HOOK_MISSING`: central registry remains `MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN`; no real socket consumer or route-to-disk regression |
| P2 committed-text source path | `AVAILABLE_AND_VERIFIED` in controlled software tests; real browser/service Agent/Tool observation was not run |
| P2 Agent/Tool runtime | `MACHINE_PRIVATE_INPUT_REQUIRED`: no registered, configured and running real Agent/Tool service plus matching model runtime was available for the browser journey |
| P3 real mutation/Executor | `MACHINE_PRIVATE_INPUT_REQUIRED`: no disposable registered Code project, matching model/configuration or runtime service |
| P3 formal voice | `IMPLEMENTATION_HOOK_MISSING`: new atomic source is unregistered and CR/Media plus no-projection arbiter composition is absent |
| Code Agent workspace support-path policy | `PRODUCT_DECISION_REQUIRED`: relocation or explicit governance for `.gitignore`, `coding_memory/`, `prompt_attachment/` and `.agent_history/` is not selected |
| X-OBS backend contract | `PRODUCT_DECISION_REQUIRED`: no backend/transport, retention, redaction, retry/shutdown or SLO policy is selected |
| X-OBS backend configuration | `MACHINE_PRIVATE_INPUT_REQUIRED`: no endpoint, credentials or runtime exporter configuration is present |
| Chrome/device journey | `PHYSICAL_USER_ACTION_REQUIRED`: no microphone/output permission, revoke, autoplay, device-loss, background/resume, reconnect or human-heard run |
| Secure deployment policy/owner | `PRODUCT_DECISION_REQUIRED`: the HTTPS/WSS reverse-proxy and allowed-origin owner is not selected |
| Secure deployment configuration | `MACHINE_PRIVATE_INPUT_REQUIRED`: no TLS, proxy, CSP/CORS, WebSocket-upgrade or allowed-origin runtime configuration is present |

Provider environment presence checks covered the seven configured Speech inputs without reading or reporting secret values; none was present. Project registration inspection found zero registered Code projects. These are machine-private observations, not Git-restored guarantees.

## D-046/D-053 review closure

The T3 Tier 3 batch completed all three D-053 passes: implementation self-review, repeated Main cold complete-diff review and an independent read-only review equivalent. A literal `/review` entry was unavailable, so the independent agent pass is the recorded substitute; no claim that `/review` ran is made.

Review findings were fixed before commit and integration:

- non-concrete/package sources could otherwise widen acceptance of non-projectable events;
- new public authority types needed explicit exports;
- source/store subclasses could otherwise forge the reserved atomic route;
- a longer source grant could diverge from the bridge grant after activation;
- cancelled close waiters could lose close intent during blocked activation;
- full event-prefix materialization could occur before the subscription capacity check.

The final implementation uses exact concrete types and authorization fingerprints, reauthorizes every downstream effect, retains close ownership and rejects an oversized authoritative head before event retrieval or runtime allocation. The independent final focused pass recorded `15/15` targeted adversarial tests, `160/160` focused tests, Ruff, compile/export checks and `git diff --check`, with no remaining finding.

Main then reviewed the integrated range and cumulative results against the Wave C request, repository rules and preserved route truth.

The final independent combined review of `107104bb..4d1672ea` plus the three-document closure diff returned `PASS AFTER FIXES — EQUIVALENT` with no remaining actionable finding. It independently verified Git/task-worktree facts, matching T3 source/integration trees, authority/sequence/boundedness claims, `985/985` backend tests, `200/200` frontend tests, the 4507-module production build, Ruff, relative Markdown links across all 45 Live Voice Markdown files, zero tracked documentation duplicates, archive warnings and `git diff --check`. This was a read-only equivalent because literal `/review` was unavailable. It did not perform a real Provider/device/Agent/Tool/Executor/deployment/X-OBS journey or an external hosting audit, and it did not pre-approve a documentation commit or final clean status.

## Automated verification

| Verification | Result |
|---|---|
| T1 focused Media/browser selections | `230/230 PASS` |
| T2 focused backend P2/formal-adapter/history selections | `174/174 PASS` with one warning |
| T2 frontend Conversation Runtime replica | `9/9 PASS` |
| T3 final focused selection | `160/160 PASS in 9.45s` |
| T3 targeted adversarial independent selection | `15/15 PASS` |
| T4 backend observability selections | `90/90 PASS` |
| T4 frontend observability/diagnostics selections | `30/30 PASS` |
| cumulative backend Live Voice/Gateway/Web/AgentServer selection | `985/985 PASS in 30.36s` |
| `npm.cmd run test:live-voice-integrated-web` | `83/83 PASS` |
| `npm.cmd run test:live-voice-task-bridge` | `49/49 PASS` |
| `npm.cmd run test:live-voice-task-client` | `17/17 PASS` |
| `npm.cmd run test:live-voice-task-adapter` | `19/19 PASS` |
| `npm.cmd run test:live-voice-task-monitor` | `23/23 PASS` |
| `npm.cmd run test:live-voice-core` | `9/9 PASS` |
| frontend production build | PASS: TypeScript + Vite, 4507 modules transformed |
| T3 Ruff format/check and compile checks | PASS |
| code-candidate `git diff --check` and clean status | PASS |

The six cumulative frontend suites total `200/200 PASS`. The build emitted non-blocking warnings for duplicate `empty` locale keys, stale Browserslist data and chunks over 500 kB. The first parallel evidence invocation exceeded the orchestration output window; the same backend and frontend selections were rerun individually to capture the terminal results above, with no code change between runs.

Automated tests are software evidence only. They do not prove a real Provider, physical browser/device, Agent/Tool service, Task Executor, secure deployment or observability backend journey.

## Forbidden-effect assertions

- Feature-off and unavailable paths allocate no Provider, device, Media owner, queue, worker, sink, timer, registration, network or storage effect owned by the affected lane.
- Wrong identity, task, scope, correlation, causation, generation, track, attempt, confirmation or authorization fails before protected downstream effects.
- Forged authority/store subclasses, divergent or expired grants and cancelled-close races produce zero unauthorized sink, arbiter, acknowledgement, Task or outbox effects.
- Oversized atomic prefixes perform zero event-row selection/materialization and allocate no subscription queue or worker.
- Media diagnostic paths do not expose raw audio payloads; no route-to-disk success is claimed.
- X-OBS timeout, saturation, late result and export failure do not rewrite business truth, and flag-off performs zero exporter/browser-query effects.
- Subscription detach and retained cleanup do not imply Task cancellation, human audio observation or product completion.

## Real evidence, Gate and retained blockers

Wave C generated no new sanitized real E2E evidence. No physical browser/device, live Provider, running Agent/Tool service, disposable Task Executor, deployed proxy or X-OBS backend was exercised. The source-integrated committed-text P2 route and the new P3 authority foundation were observed only in deterministic/local software tests.

Therefore the Integrated Demo remains `NOT RUNNABLE`, no Immutable Alpha Gate was run, and the Demo Replacement Ledger remains `0/100`. The acceptance authority at this review's exact source was [Integrated Demo acceptance](validation/INTEGRATED_DEMO_ACCEPTANCE.md) plus the historical `validation/ALPHA_ACCEPTANCE.md`, now recoverable from Git history; package tests and review passes cannot award their credit, and the current product-readiness contract does not retroactively replace that Alpha contract.

The consolidated user-dependent package is:

1. choose and configure the real Speech Provider and whether the product target is batch or streaming;
2. provide the registered Media termination/resampling/deployment owner and prove zero audio-payload persistence;
3. provide a registered, configured and running real Agent/Tool service with its matching model runtime for the P2 browser journey;
4. provide one disposable registered Code project, model configuration and runnable Executor/service for the P3 journey;
5. choose whether Code Agent support paths `.gitignore`, `coding_memory/`, `prompt_attachment/` and `.agent_history/` are relocated or explicitly governed for the clean-workspace Gate;
6. choose/configure the X-OBS backend plus retention, redaction, queue/retry/timeout/shutdown and SLO policy;
7. provide the HTTPS/WSS reverse-proxy, CSP/CORS, WebSocket-upgrade and allowed-origin deployment configuration;
8. perform the consolidated desktop-Chrome microphone/output, permission/revoke, autoplay, device-loss, background/resume, reconnect and human-observation journey;
9. after those paths pass on one immutable candidate, decide whether Main should fast-forward local `hx/0803_live_voice` and separately authorize any exact remote push.

Until those inputs exist, missing routes stay fail-closed and no product-complete, production-ready or Gate-eligible claim is valid.
