# Live Voice current status

> Updated: 2026-08-06
> This is the only mutable source for current branch facts, milestones, track state, blockers and next actions. Detailed tests, reviews and immutable evidence are linked rather than copied here.

## Resume capsule

- Milestones: V0 `CLOSED`; Week 1 `CLOSED`; D-031 Compatibility Adapter `CLOSED`.
- Product Gate: Integrated Demo `NOT RUNNABLE`; Replacement Ledger `0/100`.
- Routes: P1 `fallback + reviewed AIO/batch-Speech + contract-only Browser↔Gateway media seam`; P2 `reviewed real-Agent/CR + notification arbitration + trusted-context Adapter`; P3alpha `authenticated query/subscription + text/UI progress-return foundation, mutation and formal voice fail-closed`; X-OBS `correlation + bounded export-buffer foundations`; Integrated `default-off Web shell + Gate-0 truth contract + reviewed uncommitted composition-root/package-Adapter candidate, no central registration`.
- Current priority: approve and integrate the current uncommitted composition candidate, then add the default-off central registration and real trusted hooks one segment at a time. Provider/Media, II, P3 confirmation/return, X-OBS backend and Web wiring remain separate open work. Every formal route remains default-off or fail-closed until its exact authority and runtime evidence exist.
- Current integration candidate is based on `5d599c54`. It closes the Agent/CR notification-backpressure source defect and removes raw Speech audio at the current Vite dev-log persistence boundary. On this candidate, `599` cumulative Live Voice/Media Python tests, `16` frontend Speech/privacy tests, `32` Integrated Web tests, affected static/bundle checks, and production builds with the Integrated flag both off and on passed. This is still source/test integration only; no aggregate real-service, real-device or cumulative acceptance Gate has run.
- A separate uncommitted candidate on current HEAD `0fb592f3` adds the default-off composition root plus bounded P2, P3 text/progress, X-OBS and dedicated Media package Adapters. Its final cumulative focused suite passed `183/183`, final Media recheck passed `62/62`, affected static checks passed and D-053 review equivalents reported no remaining finding. It still has no central registration or real runtime journey and earns no Replacement Ledger credit.

## Package state capsule

- `CLOSED`: shared ACG/telemetry kernel, every P1/P2/P3alpha A package, deterministic fake verticals, Browser P1 fallback and bounded D-031 Compatibility Adapter.
- `FOUNDATION ONLY`: the prior P1/P2/P3alpha/X-OBS foundations are now joined by the cross-language product-composition Gate (`a7b2a939`), trusted ProductAuthority foundation (`be9374cc`), Provider-neutral Browser↔Gateway media seam (`214a3139`) and fail-closed Task progress-return bridge (`5d599c54`). The current uncommitted candidate adds a reviewed composition root and bounded P2/P3/X-OBS/Media package Adapters. They define integration contracts and safe unavailable paths; none is centrally registered as a complete formal product route or earns Replacement Ledger credit.
- `PARTIAL / STILL OPEN`: AIO-C still lacks real-device latency/failure closure; the current Vite JSON sink is sanitized and a dedicated binary Media package seam exists, but central route registration and its real route-to-disk logger regression do not. TC-C and X-OBS remain product-unwired. SR-C, SS-C, RM-B/C, II-B/C, trusted production identity/resolver, P3 confirmation issuance, atomic voice-progress handoff, final product wiring and real-service evidence remain open.
- `CROSS-CUTTING PARTIAL`: X-OBS now has correlated Python/TypeScript facts plus bounded buffering, and X-E2E/X-WEB has a guarded diagnostics/composition shell; no exporter consumer/backend or cumulative real journey is wired.

## Git and release identity

- Development branch: `hx/0803_live_voice`; upstream: `origin/hx/0803_live_voice`. Resolve HEAD, divergence and dirty state dynamically at resume.
- The six product-foundation feats run from formal batch Speech `c85979bd` through the cumulative Web shell `19dadc13`. The subsequent bounded P1/P2/P3alpha/X-OBS commits `72023158`, `16243d26`, `b8dbb9c4` and `afec02ce` are linearly integrated on the branch; this is source integration, not product-route closure.
- The reviewed Gate-0/Authority/Media/Progress batch is linearly integrated as `a7b2a939`, `be9374cc`, `214a3139` and `5d599c54`. Its contracts remain default-off, injected or unavailable until the product composition owner supplies the missing runtime authorities and hooks.
- Reviewed foundations are reconciled as AIO-B `e407af45` → `50b98b4a`, CR-B `4b384970` → `1d721ca0`, and AB-B `a7ec6bad` → `3d357c2e`; their review records own the exact fixes and verification.
- V0 immutable Released/Frozen baseline: `ee2896a4afb186e693c720476b6de10797e66f72`, Gate 0–6 PASS.

Git source and tests are the implementation fact. If Git and this file disagree, report the gap and repair this file rather than following stale prose.

## Accepted product target and schedule meaning

D-046 defines one cumulative engineering route and D-055 makes the current product carrier **Integrated Web Alpha**:

1. **V0 — complete and frozen:** real microphone → committed transcript → real JiuwenSwarm Agent/Tool → truthful final → speech.
2. **W2 — cumulative Integrated Demo Gate:** P1, P2, P3alpha, Context, Progress, Failure/Degradation and Observability run in one product path and reach at least 90/100 with mandatory invariants.
3. **W3/W4 — Integrated Web Alpha Gate:** real P1/P2/P3alpha verticals, desktop Web platform evidence and the joint non-blocking interaction/progress Gate pass on one immutable candidate.
4. **Later:** complete P3, D1/D2, production authorization, wider browsers/platforms, operational SLOs, privacy/retention and release hardening.

`W2/W3/W4` are dependency and delivery-order windows, not current calendar promises. The original three-to-four-week estimate assumed at least three useful implementation lanes. D-052 remains the default single-lane policy, with explicit user-approved bounded exceptions under one Integration Owner: the earlier TC-B/ED-B/VB-B batch and the completed P1/P2/P3alpha/X-OBS batch. These completed exceptions do not automatically authorize new concurrent coding scopes. No replacement calendar estimate is accepted yet. The stable package map and historical one-engineer timeboxes are in the [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md).

The carrier is the JiuwenSwarm desktop Web frontend. D-058 freezes the first Alpha compatibility promise to one desktop Google Chrome baseline. Every candidate must still record exact Chrome/OS/origin/device/network facts; Chrome/Chromium 107 remains only the implementation floor. Edge, other Chromium builds, Firefox, Safari, mobile Web, PWA, WebView2 and native clients are outside the current Alpha promise. Deployed Alpha requires a secure context and Gateway-held Provider credentials.

## External planning-label mapping

- `Confirm the product scope and key technical choices` maps to the architecture/decision and X-WEB scope Gate. The current Alpha product scope, carrier, Chrome baseline and AIO choice are accepted; Speech Provider, media transport/codec and production deployment/auth choices remain package-owned open decisions, so the combined label is `PARTIAL` unless it means only the kickoff scope decision.
- `Build a production-ready voice flow` maps across W2/W4 P1/P2/X-E2E/X-WEB/X-OBS and the later Production hardening scope, with P3 included when background work is part of the journey. V0 proves only a demo-grade flow; this label remains `OPEN`.

## Current delivery dashboard

| Track | Current implementation fact | Next bounded work | Dependency / limit |
|---|---|---|---|
| Shared contract | ACG v2 critical kernel, fixtures/fakes/conformance and route telemetry are committed and reviewed; strict Python/TypeScript ContextRef and source-backed WorkProgress v2 parity are integrated | keep stable while real consumers integrate | ContextRef authorization/expiry/redaction enforcement remains consumer-owned; no replacement credit from contract/fake evidence alone |
| P1 Speech I/O | AIO/batch-Speech foundations have a trusted Speech-authority Adapter and exact LVM1 Browser↔Gateway media contract; the current uncommitted candidate adds a same-origin package-only binary route while the Vite JSON boundary removes raw Speech audio | centrally register and prove the dedicated non-logging route, select/configure the Provider, then inject the real resolver and wire capture/playout | package tests do not prove a real route-to-disk path; streaming SR-C/SS-C, Provider/device/latency evidence and P1 credit remain open |
| P2 Realtime | D-059 real-Agent/CR, notification arbitration and ProductAuthority pre-allocation context foundations are source-integrated; an uncommitted Adapter candidate binds one trusted authority result through package activation and retained cleanup | register the Adapter under authenticated context, compose RM/II/runtime/arbiter and prove PresentationAck/history plus the real Agent/media journey | the source-level queue blocker is closed, but there is no central product registration, authenticated external Agent/Tool journey or P2/Web credit |
| P3alpha Task | Query/subscription foundations have exact ProductAuthority P3 adapters and a generation-fenced TaskEvent→text/UI bridge; the uncommitted product Adapter candidate adds authenticated read-only query and text progress wiring | centrally inject the Web session/live subscription/text sink, supply the trusted confirmation issuer and design the atomic source/projection handoff required for voice | mutation remains closed; formal voice is `TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE`; no fabricated replay/resequence is permitted |
| Integration / X-OBS | Gate-0 freezes route truth and cumulative order; the uncommitted candidate adds a default-off authority-first composition root plus privacy-fenced bounded X-OBS package consumption | integrate the candidate, add central registrations and resolve the X-OBS nonformal-route/worker-lease lifecycle before wiring the exporter/backend and actual-route diagnostics | no central Adapter registration, exporter sink/retention/SLO backend, Chrome/device/service journey or runnable Integrated mode |

V0 and task compatibility code remains fallback, `demo_substitute` or Compatibility Adapter under D-047. Do not add formal authority to `useLiveVoiceDemo`, the frontend TaskBridge or legacy `schedule.*`/JSON state. CR/TC/ED and the target modules must take ownership through incremental replacement.

## D-031 current state

D-057 accepts D-031 as `CLOSED` for its bounded Compatibility Adapter scope: one page-memory task, one in-flight read, exact-key reconciliation, strict task/target/provenance checks, bounded retry, truthful terminal state, no Chat mutation and safe at-most-once terminal speech. It does not grant formal TC/ED/VB authority or replacement credit.

D-056 binds execution to the selected persisted project, Code Agent root and Git top-level. Each task uses a fresh restricted Session, rejects shell/test/Git requirements before creation, cleans up on every exit and requires a Git-visible selected-project effect. Mismatch, invalid target, zero effect, ignored-only effect and foreign-root-only effect fail closed.

The accepted isolated run proves that bounded contract and records its limitations. Exact commands, IDs, retry behavior, mutation, automated matrix and review passes remain in the [implementation review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md) and [sanitized evidence](evidence/D031_20260805_PROJECT_BOUND.md). Workspace support paths, eventual terminal notification and Speech fidelity remain follow-ups under their owning tracks.

## Demo Replacement Ledger

The [Integrated Demo acceptance](validation/INTEGRATED_DEMO_ACCEPTANCE.md) owns scoring. Current credit remains zero because no formal real route has completed its required acceptance evidence.

| Weighted journey | Weight | Current route | Credit | Formal replacement condition |
|---|---:|---|---:|---|
| P1 capture, recognition, synthesis, playout | 20 | Browser Speech/TTS fallback | 0 | AIO/SR/SS real Adapter evidence |
| P2 lifecycle, non-blocking work, fence/history | 40 | local hook/epoch and legacy Chat path | 0 | CR/RM/II/AB own and prove the route |
| P3alpha create/control/events/progress | 25 | schedule Bridge/card plus D-031 polling substitute | 0 | TC/ED/VB real Core/Event/Executor path |
| Context, degradation, observability, flag-off | 15 | partial disclosure and legacy logs | 0 | versioned facts, correlated trace and tested fallback |
| **Total** | **100** | scoring has not started | **0** | W2 requires at least 90 and every mandatory invariant |

## Execution and review policy

- D-052 keeps design, implementation, tests and review in the current GPT/Sol lane. Do not switch or delegate to DeepSeek or another external execution model; historical candidates are reference material only.
- D-052 currently describes one implementation lane and does not by itself authorize multiple simultaneous coding agents. Parallel coding requires an explicit newer execution decision with non-overlapping package/file ownership and one integration owner.
- The user-approved TC-B/ED-B/VB-B batch and the later P1/P2/P3alpha/X-OBS batch were bounded exceptions with non-overlapping file ownership and one Integration Owner. Both are complete at the Git-integration boundary; neither authorizes additional concurrent scopes or broadens package authority.
- Further work may run in parallel only after the Integration Owner freezes shared authority/contracts and assigns non-overlapping package/file boundaries. Product composition and authority may advance together; Provider/Media, II, VB-C, UI, X-OBS backend and deployment may advance independently where those boundaries hold. Final activation and cumulative Gate evidence remain integration-owned closure work.
- D-053 requires Tier 2/3 batches to complete self-review, cold complete-diff review and independent `/review` or a recorded equivalent. Tier 1 normally uses the first two unless risk is raised.
- Related files in one coherent boundary may share review and commit. Every commit and push still requires separate exact approval under root `AGENTS.md`.

## Known blockers and machine-private conditions

- D-031's bounded validation is complete. Shared Code Agent runtime files currently land inside the selected project; Agent Runtime/workspace isolation must relocate or explicitly govern `.gitignore`, `coding_memory/`, `prompt_attachment/` and `.agent_history/` before a formal clean-workspace Gate can pass.
- D-031 terminal audio is safe at most once and may be skipped when no immediate safe gap exists; the new notification arbiter is not wired to D-031/CR, so guaranteed/eventual terminal notification remains unavailable in the product path.
- D-058 selects the single-desktop-Chrome range and AIO-B design. One controlled Chrome/default-microphone normal path passed, but permission revoke, device loss, background lifecycle and AIO-C latency still lack real evidence. Selected streaming Speech Provider, Browser↔Gateway media transport and deployed secure-origin evidence remain open.
- Integrated cumulative mode is not implemented. A reviewed uncommitted composition-root candidate now owns default-off activation/cleanup semantics, but there is no central product registration or real route. The Web shell remains a truthful diagnostics boundary; current V0, stable-sentence and task modes remain separate compatibility/Demo routes.
- Critical-token clarification and once-only dispatch are implemented and tested only as an unwired package. Browser Speech fidelity remains weak for critical Chinese and technical tokens, so no protected product path may bypass that Gate once composition begins.
- Existing task scope is single-user request consistency, not production authorization; JSON guarantees are same-process, not exactly-once.
- Current supplement/cancel behavior is not a production generation or Agent/Tool side-effect fence.
- D-059's real-Agent/Harness/CR foundation passed its three review equivalents after fixes, but remains product-level `PARTIAL` until authenticated composition and cumulative real browser/media/service evidence.
- `MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN`: the known Vite development JSON logger leak is fixed at its write boundary, and the uncommitted dedicated binary route proves zero calls to its injected logger/file hooks in package tests. No centrally registered real route-to-disk regression exists. Formal media remains unavailable until that exact runtime path proves zero audio-payload persistence.
- Formal batch Speech remains fail-closed because the current Web connection has request-asserted rather than authenticated identity. The ProductAuthority foundation and package-only non-logging Media seam exist, but no real trusted resolver, central product injection or registered runtime transport exists.
- P3alpha query composition is present, but production task mutation remains intentionally closed because there is no trusted confirmation issuer; real project, restart and reconciliation evidence is also outstanding.
- X-OBS has bounded export buffering but no product consumer, export sink/transport, retention policy or SLO backend, and the cumulative Web shell has not been exercised with real Adapters, Chrome, devices or services.
- A repository-local `.venv` directory and restored frontend dependencies are present on this machine, but their usability, credentials, Provider configuration, project registration, runtime data, browser permissions/devices and network state are machine-private and are not Git-restored guarantees.

## Detailed evidence routes

- Week 1 implementation and review: [W1-K1](W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md), [A packages](W1_A_PACKAGE_REVIEW_2026-08-04.md), [W1-X2/P1B](W1_X2_P1B_REVIEW_2026-08-04.md).
- D-031 review and sanitized real-service evidence: [implementation review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md), [project-bound closure run](evidence/D031_20260805_PROJECT_BOUND.md).
- AIO-B/X-WEB decision, implementation and evidence: [AIO_B_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md](AIO_B_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md).
- CR-B runtime loop, presentation truth and review evidence: [CR_B_RUNTIME_IMPLEMENTATION_REVIEW_2026-08-05.md](CR_B_RUNTIME_IMPLEMENTATION_REVIEW_2026-08-05.md).
- WorkProgress v2 and AB-B runtime foundation review/evidence: [AB_B_WORK_PROGRESS_IMPLEMENTATION_REVIEW_2026-08-05.md](AB_B_WORK_PROGRESS_IMPLEMENTATION_REVIEW_2026-08-05.md).
- Frozen P2 real Agent/Harness interface execution contract: [P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md](roadmap/P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md).
- Formal batch Speech foundation and fail-closed authority review: [P1_FORMAL_SPEECH_IMPLEMENTATION_REVIEW_2026-08-05.md](P1_FORMAL_SPEECH_IMPLEMENTATION_REVIEW_2026-08-05.md).
- D-059 real Agent/Harness/CR implementation and review: [P2_REAL_AGENT_CR_BLOCKER_REVIEW_2026-08-05.md](P2_REAL_AGENT_CR_BLOCKER_REVIEW_2026-08-05.md).
- Formal P3alpha backend Core/Store/Executor/policy review and evidence: [P3ALPHA_REPLACEMENT_REVIEW_2026-08-05.md](P3ALPHA_REPLACEMENT_REVIEW_2026-08-05.md).
- Authenticated P3alpha composition review: [P3_AUTH_COMPOSITION_IMPLEMENTATION_REVIEW_2026-08-05.md](P3_AUTH_COMPOSITION_IMPLEMENTATION_REVIEW_2026-08-05.md).
- Speech critical-token safety review: [SPEECH_CRITICAL_TOKEN_SAFETY_REVIEW_2026-08-05.md](SPEECH_CRITICAL_TOKEN_SAFETY_REVIEW_2026-08-05.md).
- Cumulative Web shell/diagnostics review: [X_E2E_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md](X_E2E_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md).
- Correlated observability foundation review: [X_OBS_IMPLEMENTATION_REVIEW_2026-08-05.md](X_OBS_IMPLEMENTATION_REVIEW_2026-08-05.md).
- Latest bounded P1/P2/P3alpha/X-OBS code: `72023158`, `16243d26`, `b8dbb9c4`, `afec02ce`; [the repository-local index](LATEST_FOUNDATIONS_D053_REVIEW_2026-08-06.md) records exact SHA/ancestry/file scope and retained task-evidence limits without overstating independent D-053 acceptance.
- Product composition sequencing, evidence vocabulary and cumulative smoke contract: [Gate-0 record](roadmap/PRODUCT_COMPOSITION_GATE_0_2026-08-06.md).
- Current uncommitted composition root and bounded P2/P3/X-OBS/Media package review: [product-composition foundations review](PRODUCT_COMPOSITION_FOUNDATIONS_REVIEW_2026-08-06.md).
- V0 immutable evidence: [V0_20260802_ee2896a4.md](evidence/V0_20260802_ee2896a4.md).
- Environment and operating procedures: [E2E_RUNBOOK.md](runbooks/E2E_RUNBOOK.md).

## Next actions

1. Review and, with explicit approval, commit the current uncommitted composition-root and P2/P3/X-OBS/Media package candidate; do not activate formal Media.
2. Add the default-off central registration and inject the trusted Authority plus compatible P2/P3/X-OBS hooks one at a time, running cumulative route/correlation/fallback/flag-off smoke after each.
3. In parallel within frozen ownership, select/configure the Speech Provider; wire and prove the dedicated Media route-to-disk boundary; complete II, trusted confirmation issuance, P3 return and X-OBS backend boundaries. Keep formal voice unavailable until an atomic TaskEvent/projection handoff exists.
4. Register P1 Media only after its logger stop closes, then run one real desktop-Chrome/service journey covering microphone/playout, Provider, JiuwenSwarm Agent/Tool, project Task, exact cancel, PresentationAck/history, restart/reconciliation, exporter evidence and secure deployment before changing the `0/100` ledger or any Gate state.
