# X-E2E + X-WEB cumulative route shell implementation review

> Task: `X-E2E-X-WEB`
>
> Branch/worktree: `codex/lv-x-e2e-web` / independent worktree from `1e76dbd6aa0ebb011842f31beb98ca2cb11d2496`
>
> Record role: **frozen worker-candidate review; landed state, acceptance and Replacement Ledger credit remain owned by the integration session and `STATUS.md`**
>
> Commit identity: the original candidate is `0e01acc4e8fc29759c87883f7965b06fdf7d812d`; its bounded teardown, rollback-order and permission-listener corrections were committed separately as `116ab8005e68efd4f1aa68cc873188284b78b8f6`.

## 1. Original request and bounded outcome

Build the single-desktop-Google-Chrome cumulative Integrated Web route shell. The shell must represent P1 speech I/O, P2 realtime conversation and P3alpha task control in one persisted Session; select only an explicitly requested `formal`, `fallback`, `demo_substitute` or `unsupported` class; expose platform diagnostics, fault injection and flag-off behavior; and provide an injection seam for the other workers' later real implementations.

This candidate delivers the product-facing composition shell, not the missing real route. At the base SHA, the current Browser Speech and text Chat/E2A predecessors remain `fallback`, D-031 TaskBridge remains `demo_substitute`, and each is `manifest_only`. The UI says that these facts do not prove a cumulative runtime, microphone capture, physical hearing, Agent cancellation, task completion, Integrated Demo Gate or Web Alpha Gate. `gate_claim` is always `NONE`; this candidate grants no Replacement Ledger credit.

## 2. Consumed authority and risk

- Current authority/router: [`README.md`](README.md) and [`STATUS.md`](STATUS.md).
- Stable package route: [`roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md`](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md), X-E2E/X-WEB rows and dependency tree.
- Delivery and Gate model: [`roadmap/POST_V0_DELIVERY_ROADMAP.md`](roadmap/POST_V0_DELIVERY_ROADMAP.md), cumulative route and Gate sections.
- Current decisions: D-055 and D-058 in [`decisions/DECISIONS.md`](decisions/DECISIONS.md).
- Acceptance consumers: [`validation/INTEGRATED_DEMO_ACCEPTANCE.md`](validation/INTEGRATED_DEMO_ACCEPTANCE.md), [`validation/ALPHA_ACCEPTANCE.md`](validation/ALPHA_ACCEPTANCE.md), [`demo/INTEGRATED_SHOWCASE.md`](demo/INTEGRATED_SHOWCASE.md) and the Web/Integrated sections of [`runbooks/E2E_RUNBOOK.md`](runbooks/E2E_RUNBOOK.md).

The candidate owns cumulative route selection, a shared frontend entry, Session/correlation facts, resource leases and lifecycle concurrency. The eventual product route and release Gate are authority-sensitive Tier 3. The batch therefore follows the D-046 Tier 3 dimensions and D-053 three-pass review even though its default current route is non-mutating and manifest-only.

## 3. Frozen implementation contract

### Route selection and provenance

- Exactly three segment IDs exist: `p1.speech_io`, `p2.realtime_conversation`, and `p3alpha.task_control`.
- The policy requests one exact implementation class per segment. Missing or unavailable requested classes become explicit `unsupported`; the registry never silently chooses another available class.
- A selected record carries requested/actual class, owner, provider, contract version, safe reason, adapter ID, capabilities, Session/correlation facts and one of `activation_seam`, `manifest_only` or `unavailable`.
- Duplicate segment/class registrations reject as ambiguous. Formal registration requires complete formal provenance under the existing route telemetry contract.
- `formal_seams` means only that all three formal Adapters expose activation functions. `activation_leases_active` means only that the three injected lease opens completed; neither name claims runtime wiring, business success or Gate evidence.

### Activation and cleanup

- Activation requires the feature flag, a persisted Session, three available exact-class routes and an activation seam for every segment.
- Concurrent activation calls coalesce. Every activation receives an `AbortSignal`; a close request aborts cooperative pending work, fences pending activation after its current await, rolls back opened leases and prevents later segments from opening.
- Activation faults roll back in reverse order. Failed rollback/close leases are stored in acquisition order so every retry remains dependency-safe LIFO; they block a new activation until cleanup succeeds.
- Close is idempotent, serialized and best-effort across all leases. Its wait is bounded to a validated 1–60,000ms configuration (default 5,000ms): timeout returns `ROUTE_CLOSE_TIMEOUT`, keeps the underlying teardown coordinated, exposes `teardown_state=pending`, and blocks activation until cleanup becomes terminal. Timeout never claims a resource closed.
- Adapter activation/close is the only effectful shell surface; the shell has no Agent, Tool, Task, audio or history business API.

### Diagnostics and UI

- Diagnostics report browser evidence and version, declared desktop-Google-Chrome candidate scope, reported platform, secure-context/origin scope, microphone permission, enumerated input/output presence, user activation, page visibility/discard state, network state and the existing AIO capability facts.
- User-agent evidence is a candidate disclosure, not capability or Gate proof. Device labels and IDs never enter the snapshot.
- Permission/device/listener failures stay `unknown`, `unsupported`, explicit error facts or a failed monitor start. Permission listener registration failure cleans a partially registered listener and persists `MICROPHONE_PERMISSION_LISTENER_REGISTRATION_FAILED` in monitor snapshots. Stop fences late snapshots and permission listeners, including stop/restart races.
- The default-off `VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB` mounts the panel at both Chat composer locations only when enabled. Flag-off therefore leaves the existing V0, Browser fallback and task compatibility UI paths unchanged.

## 4. Scenario oracle

| ID    | Scenario                                                            | Required result                                                                                               | Forbidden effect                                                           |
| ----- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| P-01  | three deterministic fake Adapters requested as `demo_substitute`    | one degraded manifest; three leases open/close once; `gate_claim=NONE`                                        | formal/release claim or Agent/Tool/Task/audio/history mutation             |
| P-02  | three injected formal Adapters                                      | exact v2 provenance and `formal_seams`; activatable through the generic seam                                  | claim that the other workers are already product-composed or Gate-accepted |
| P-03  | current browser/text/task predecessors                              | `fallback`, `fallback`, `demo_substitute`, all `manifest_only`                                                | fake/compatibility path relabelled formal or runnable cumulative success   |
| N-01  | requested formal class absent while fallback exists                 | explicit `unsupported/REQUESTED_ROUTE_CLASS_UNAVAILABLE`                                                      | automatic fallback selection or Adapter open                               |
| N-02  | missing Session, disabled capability or injected unavailability     | explicit unsupported facts; activation rejects                                                                | partial Adapter open or business mutation                                  |
| N-03  | invalid policy/provenance/lease or ambiguous registry               | stable validation rejection                                                                                   | guessed identity, owner, provider or implementation class                  |
| F-01  | integrated flag off                                                 | three `FEATURE_DISABLED` facts in the pure shell and zero diagnostic/resource effect; product panel unmounted | change to existing Chat, V0, Browser Speech or Task behavior               |
| C-01  | concurrent activate calls                                           | one open per segment and one shared result                                                                    | duplicate live lease authority                                             |
| C-02  | close during pending activation                                     | current late lease closes; no later segment opens                                                             | stale activation resurrection                                              |
| C-02a | close during cooperative pending activation                         | Adapter receives abort; activation returns stable fenced failure                                              | later segment open or raw Adapter abort exposed as product success         |
| C-02b | close during non-cooperative pending activation                     | bounded timeout; teardown remains `pending`; activation stays blocked; late lease is closed                   | infinite close wait, false closed fact or second activation                |
| C-03  | close or activation rollback failure                                | failed lease retained for retry; new activation rejected                                                      | leaked lease forgotten or overwritten                                      |
| C-03a | multiple rollback closes fail                                       | initial close and retry both remain P2-before-P1 LIFO                                                         | retry order reversal                                                       |
| D-01  | secure desktop Chrome-like environment                              | bounded browser/origin/permission/device/activation/lifecycle/network/AIO facts                               | device label/ID, physical-heard or microphone-captured claim               |
| D-02  | denied/failed/unsupported browser queries                           | explicit denied/unknown/unsupported/error facts                                                               | success inference                                                          |
| D-03  | monitor stop/restart and late async result                          | all listeners removed and old lifecycle fenced                                                                | late snapshot/listener mutation                                            |
| D-03a | permission query succeeds but listener registration throws          | granted fact plus stable listener-registration diagnostic; partial listener removed                           | empty diagnostic success or leaked listener                                |
| U-01  | rendered route panel                                                | all three classes/reasons and non-success warning are visible                                                 | “microphone heard”, “Agent cancelled” or “task completed” assertion        |
| R-01  | default and flag-on frontend builds plus affected Live Voice suites | both compile/build and existing paths remain green                                                            | shared entry break or task/browser regression                              |

For every scenario, forbidden Agent, Tool, Task, business cancellation, audio/history authority and persistence effects are zero unless a future injected Adapter explicitly owns and proves them under its own contract.

## 5. Source ownership and exclusions

Owned candidate source:

- `frontend/src/features/live-voice/formal/integratedWebRouteShell.ts`
- `frontend/src/features/live-voice/formal/webPlatformDiagnostics.ts`
- `frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx` and its package-local CSS
- the two guarded ChatPanel mount points, the new feature flag/type, English/Chinese disclosures, focused tests and package test script
- this implementation review record

Explicit exclusions:

- no SR/SS, Agent/CR, P3 Core, speech safety or X-OBS reimplementation;
- no Provider/Gateway credentials, endpoint, media transport, real microphone/playout action or external service run;
- no real Task creation/cancellation, Agent execution, tool call, Chat/history mutation or success inference;
- no change to `STATUS.md`, `README.md`, decisions, roadmaps, validation sources or Replacement Ledger;
- no claim that file presence, unit tests, this branch or a future commit is runtime-wired, product-composed, verified or Gate-accepted;
- no commit, push, merge, rebase or cherry-pick without the repository's exact approval gates.

## 6. Integration handoff seam

The integration session should compose returned real modules by constructing one `IntegratedWebAdapterRegistry` and one exact `IntegratedWebRoutePolicy`. Each real module contributes an `IntegratedWebRouteAdapter` with its real owner/provider/contract/capabilities/availability and optional activation lease; it must not be copied into this package. `LiveVoiceIntegratedRoutePanel` accepts an optional `routeSelection`, so the shared composition root can inject the reconciled registry/policy without changing the shell or relabelling current compatibility Adapters.

Expected reconciliation points after the five real commits arrive:

1. Register the accepted P1 speech I/O Adapter(s) against `p1.speech_io`; choose `formal` only if the returned contract/provenance and runtime path support that class.
2. Register the accepted P2 realtime conversation/Agent Adapter against `p2.realtime_conversation`; preserve persisted Session and correlation facts and do not infer Agent action from UI intent.
3. Register the accepted P3alpha Core/safety Task Adapter against `p3alpha.task_control`; retain exact task/command identity and separate stop/cancel/completion authority.
4. Let the X-OBS package consume the manifest/diagnostic facts through its own seam; this candidate neither implements nor grants observability/release credit.
5. Pass the reconciled `routeSelection` at the product composition root, keep `VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB` default-off until integration acceptance, then run the real single-Chrome cumulative journey and applicable Gates.

Likely conflicts are the two ChatPanel mount locations, `featureFlags.ts`, `vite-env.d.ts`, locale objects and `package.json`. Resolve them by retaining other workers' behavior and adding this guarded shell; do not replace their real routes with `createCurrentIntegratedWebRouteSelection`, which is only the truthful base-SHA predecessor manifest.

## 7. Review and evidence ledger

| Pass                           | State                           | Findings/fixes/evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------------------------ | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Implementation self-review     | `PASS AFTER FIXES`              | Complete source/test inspection removed overclaiming `ready/runtime_wired/cumulative_runtime_active` names; preserved null legacy contract facts for unavailable compatibility Adapters; distinguished enumerated devices from physical availability/hearing; refreshed dynamic network/user-activation/route timestamps; made listener setup cleanup-safe; retained failed close leases; serialized activation/close; fenced and abort-signalled close-during-activation; blocked activation over failed cleanup; and fenced prior-lifecycle permission listeners. Focused regression tests were added for every semantic fix.                            |
| Cold complete-diff review      | `PASS AFTER FINAL REPEAT`       | The first packet/rules/base/source/test comparison found that the UI omitted collected secure-context/discarded-page and Session/provider/contract facts, its English warning did not explicitly deny real microphone capture/physical hearing, and pending Adapter activation had no cooperative cancellation signal. It also found two incorrect relative links in this record. The UI, contract, tests and links were fixed. A complete tracked/untracked diff repeat after the AbortSignal semantic change found no remaining actionable defect or unowned business mutation.                                                                          |
| Independent review substitute  | `PASS WITH EXPLICIT LIMITATION` | The packaged `codex.exe` returned Windows `Access is denied` even for `codex --version`/`codex review --help`, and no callable `/review` tool was exposed; the Codex unstaged review panel is only a diff viewer. Exact substitute: a second read-only adversarial complete-diff audit in that panel, plus scoped authority/effect scans and packet-to-scenario-to-test traceability. It found no additional issue. This was the same Worker/model, not an organizationally independent reviewer; it does **not** claim `/review` ran, and the integration owner should run a true independent review if required for Gate acceptance.                     |
| Integration review correction  | `PASS AFTER FIXES`              | Integration review of `0e01acc4` found three actionable defects: unbounded close wait for non-cooperative activation, failed rollback leases stored in retry-reversed order, and a silent permission-listener registration failure. The correction separates bounded caller wait from retained teardown ownership, exposes `pending/cleanup_required`, blocks reactivation, preserves acquisition order for every LIFO retry, and persists/cleans the listener-registration failure. Self-review additionally prevented an active route's ordinary leases from being mislabeled `cleanup_required` and capped close wait configuration at 60 seconds.      |
| Correction cold complete-diff  | `PASS AFTER FINAL REPEAT`       | The correction diff was re-read against all three integration findings, the original packet, repository rules, committed behavior and actual rerun evidence. The first correction pass found that ordinary active leases were being mislabeled `cleanup_required`; it also strengthened the permission-listener test to prove the diagnostic survives later refreshes. After those fixes, the final complete-diff repeat found no remaining actionable defect, false closed fact, LIFO inversion, silent listener failure or forbidden business mutation.                                                                                                  |
| Automated verification         | `PASS WITH LINT LIMITATION`     | Correction focused strict TypeScript + SSR UI bundle + Node suite passes 32/32. Correction affected regressions pass 134/134: shared contract v2 30, Browser AIO 39, SpeechRecognition lifecycle 7, TaskBridge 49, Chat streaming 3 and historical Tool settlement 6. Frontend `tsc --noEmit` plus default flag-off and explicit flag-on Vite production builds pass. Affected Prettier, `git diff --check` and this record's relative Markdown links pass after the final cold review. `npm run lint` remains unable to inspect source because ESLint 8.57.1 cannot find a repository configuration file; this is a recorded limitation, not a lint pass. |
| Real Chrome / service evidence | `NOT RUN`                       | Deterministic browser fakes verify diagnostics and UI disclosure. A controlled real desktop Google Chrome permission/device/autoplay/page-lifecycle run, real Adapter composition, provider/Agent/Task journey and all release evidence remain integration-stage work.                                                                                                                                                                                                                                                                                                                                                                                     |

### Integration Owner re-review of the correction commit

The Integration Owner re-reviewed correction commit `116ab8005e68efd4f1aa68cc873188284b78b8f6` and returned `CODE PASS / REVIEW RECORD CORRECTION REQUIRED`. All three original code defects were confirmed fixed; no source or test changes were requested. The sole remaining finding was the stale line 9 claim that the correction was uncommitted, which this documentation-only batch corrects.

Owner-run verification passed: focused Integrated Web tests 32/32, affected regressions 134/134, default flag-off and explicit flag-on production builds, affected Prettier, `git diff --check`, and an additional non-cooperative `lease.close` bounded-wait probe.

This record does not update mutable project status. At this worker-review snapshot, integration had not yet reconciled real commits or run the required evidence, so the record granted no runnable Integrated Demo claim or Replacement Ledger credit. Later state belongs only in STATUS.
