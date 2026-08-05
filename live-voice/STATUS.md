# Live Voice current status

> Updated: 2026-08-05
> This is the only mutable source for current branch facts, milestones, track state, blockers and next actions. Detailed tests, reviews and immutable evidence are linked rather than copied here.

## Resume capsule

- Milestones: V0 `CLOSED`; Week 1 `CLOSED`; D-031 Compatibility Adapter `CLOSED`.
- Product Gate: Integrated Demo `NOT RUNNABLE`; Replacement Ledger `0/100`.
- Routes: P1 `fallback + AIO foundation`; P2 `formal foundations only`; P3alpha `Compatibility Adapter + reviewed formal backend foundation`; Integrated `unavailable`.
- Current priority: add authenticated product composition for the reviewed P3alpha backend while keeping the formal mutation route disabled until that authority exists.
- Next independent slices: Speech critical-token safety; D-059 now unblocks the real Agent Adapter + CR notification consumer for P2 under its frozen interface Task Packet.
- Verified code base: `250ffa6` (pre-P3alpha reviewed code base); current P3alpha backend affected verification `PASS`. Detailed evidence is linked below.

## Package state capsule

- `CLOSED`: shared ACG/telemetry kernel, every P1/P2/P3alpha A package, deterministic fake verticals, Browser P1 fallback and bounded D-031 Compatibility Adapter.
- `FOUNDATION ONLY`: AIO-B, CR-B and AB-B are committed; the reviewed TC-B/ED-B/VB-B backend batch joins them in this integration. None is a complete formal product route or earns Replacement Ledger credit.
- `OPEN`: AIO-C, SR-B/C, SS-B/C, RM-B/C, CR-C, II-B/C, TC-C and VB-C, plus the remaining real Agent, product-composition and return-wiring work inside the B foundations.
- `CROSS-CUTTING PARTIAL`: X-OBS has vocabulary only, X-E2E has fake verticals only, and X-WEB has the carrier/Chrome/AIO baseline only.

## Git and release identity

- Development branch: `hx/0803_live_voice`; upstream: `origin/hx/0803_live_voice`. Resolve HEAD, divergence and dirty state dynamically at resume.
- Reviewed foundations are reconciled as AIO-B `e407af45` → `50b98b4a`, CR-B `4b384970` → `1d721ca0`, and AB-B `a7ec6bad` → `3d357c2e`; their review records own the exact fixes and verification.
- V0 immutable Released/Frozen baseline: `ee2896a4afb186e693c720476b6de10797e66f72`, Gate 0–6 PASS.

Git source and tests are the implementation fact. If Git and this file disagree, report the gap and repair this file rather than following stale prose.

## Accepted product target and schedule meaning

D-046 defines one cumulative engineering route and D-055 makes the current product carrier **Integrated Web Alpha**:

1. **V0 — complete and frozen:** real microphone → committed transcript → real JiuwenSwarm Agent/Tool → truthful final → speech.
2. **W2 — cumulative Integrated Demo Gate:** P1, P2, P3alpha, Context, Progress, Failure/Degradation and Observability run in one product path and reach at least 90/100 with mandatory invariants.
3. **W3/W4 — Integrated Web Alpha Gate:** real P1/P2/P3alpha verticals, desktop Web platform evidence and the joint non-blocking interaction/progress Gate pass on one immutable candidate.
4. **Later:** complete P3, D1/D2, production authorization, wider browsers/platforms, operational SLOs, privacy/retention and release hardening.

`W2/W3/W4` are dependency and delivery-order windows, not current calendar promises. The original three-to-four-week estimate assumed at least three useful implementation lanes. D-052 remains the default single-lane policy; the current user-directed P3alpha batch is a bounded exception for non-overlapping TC-B/ED-B/VB-B subtracks under one integration owner. No replacement calendar estimate is accepted yet. The stable package map and historical one-engineer timeboxes are in the [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md).

The carrier is the JiuwenSwarm desktop Web frontend. D-058 freezes the first Alpha compatibility promise to one desktop Google Chrome baseline. Every candidate must still record exact Chrome/OS/origin/device/network facts; Chrome/Chromium 107 remains only the implementation floor. Edge, other Chromium builds, Firefox, Safari, mobile Web, PWA, WebView2 and native clients are outside the current Alpha promise. Deployed Alpha requires a secure context and Gateway-held Provider credentials.

## External planning-label mapping

- `Confirm the product scope and key technical choices` maps to the architecture/decision and X-WEB scope Gate. The current Alpha product scope, carrier, Chrome baseline and AIO choice are accepted; Speech Provider, media transport/codec and production deployment/auth choices remain package-owned open decisions, so the combined label is `PARTIAL` unless it means only the kickoff scope decision.
- `Build a production-ready voice flow` maps across W2/W4 P1/P2/X-E2E/X-WEB/X-OBS and the later Production hardening scope, with P3 included when background work is part of the journey. V0 proves only a demo-grade flow; this label remains `OPEN`.

## Current delivery dashboard

| Track | Current implementation fact | Next bounded work | Dependency / limit |
|---|---|---|---|
| Shared contract | ACG v2 critical kernel, fixtures/fakes/conformance and route telemetry are committed and reviewed; strict Python/TypeScript ContextRef and source-backed WorkProgress v2 parity are integrated | keep stable while real consumers integrate | ContextRef authorization/expiry/redaction enforcement remains consumer-owned; no replacement credit from contract/fake evidence alone |
| P1 Speech I/O | AIO/SR/SS Ports and Browser Speech fallback are committed; AIO-B adds a reviewed Chrome `getUserMedia`/AudioWorklet/Web Audio Adapter, exact 20ms PCM frames, lifecycle tests and one real-device normal-path run | connect the bounded Adapter only through owned SR/RM B/C packages without claiming a complete P1 route | no real SR/SS Provider or Browser↔Gateway media route; permission revoke/device loss/background and AIO-C latency lack real evidence; AIO-B alone earns no P1 credit |
| P2 Realtime | CR/RM/II/AB A packages and deterministic fake vertical are committed; CR-B owns the bounded runtime/presentation foundation, while AB-B adds bounded non-blocking Agent dispatch and source-backed round WorkProgress over an injected Adapter; D-059 freezes the five previously missing adjacent interfaces | resume the [P2 real Agent + CR Task Packet](roadmap/P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md) and connect the real Harness source through the reviewed foundations | implementation and real-facade evidence remain open; no real media route, browser PresentationAck, authenticated product composition or complete history durability; no P2/Web Gate credit |
| P3alpha Task | TC/ED/VB A packages and fake vertical are committed; the reviewed backend batch adds durable TC-B Core/Store, a project-bound ED-B Adapter foundation and strict VB-B policy over D-031's carrier | add authenticated product composition, startup/periodic reconciliation and route telemetry; close ED workspace isolation before the clean-workspace Gate | formal mutation route remains disabled; VB-C, TC-C, WorkProgress/CR return wiring and product/real-service acceptance remain open |
| Integration | three fake verticals and opt-in Browser P1 fallback exist | after one real route passes review, start cumulative integration and service validation | Integrated mode is documented but not runnable |

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
- The user-directed formal P3alpha replacement batch is the current bounded exception: TC-B, ED-B and VB-B may proceed as non-overlapping subtracks under one integration owner. It does not authorize additional concurrent coding lanes or broaden any package authority.
- D-053 requires Tier 2/3 batches to complete self-review, cold complete-diff review and independent `/review` or a recorded equivalent. Tier 1 normally uses the first two unless risk is raised.
- Related files in one coherent boundary may share review and commit. Every commit and push still requires separate exact approval under root `AGENTS.md`.

## Known blockers and machine-private conditions

- D-031's bounded validation is complete. Shared Code Agent runtime files currently land inside the selected project; Agent Runtime/workspace isolation must relocate or explicitly govern `.gitignore`, `coding_memory/`, `prompt_attachment/` and `.agent_history/` before a formal clean-workspace Gate can pass.
- D-031 terminal audio is safe at most once and may be skipped when no immediate safe gap exists; guaranteed/eventual terminal notification remains unimplemented.
- D-058 selects the single-desktop-Chrome range and AIO-B design. One controlled Chrome/default-microphone normal path passed, but permission revoke, device loss, background lifecycle and AIO-C latency still lack real evidence. Selected streaming Speech Provider, Browser↔Gateway media transport and deployed secure-origin evidence remain open.
- Integrated cumulative mode is not implemented. Current V0, stable-sentence and task modes remain separate compatibility/Demo routes.
- Browser Speech fidelity remains weak for critical Chinese and technical tokens; committed text and critical-token clarification remain required.
- Existing task scope is single-user request consistency, not production authorization; JSON guarantees are same-process, not exactly-once.
- Current supplement/cancel behavior is not a production generation or Agent/Tool side-effect fence.
- D-059 closes the P2 interface-decision blocker only. Canonical Harness round instrumentation, exact scoped cancellation, the formal no-history seam, atomic reservation and retained shutdown are not implemented or accepted until the Worker2 candidate passes review.
- A repository-local `.venv` directory and restored frontend dependencies are present on this machine, but their usability, credentials, Provider configuration, project registration, runtime data, browser permissions/devices and network state are machine-private and are not Git-restored guarantees.

## Detailed evidence routes

- Week 1 implementation and review: [W1-K1](W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md), [A packages](W1_A_PACKAGE_REVIEW_2026-08-04.md), [W1-X2/P1B](W1_X2_P1B_REVIEW_2026-08-04.md).
- D-031 review and sanitized real-service evidence: [implementation review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md), [project-bound closure run](evidence/D031_20260805_PROJECT_BOUND.md).
- AIO-B/X-WEB decision, implementation and evidence: [AIO_B_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md](AIO_B_X_WEB_IMPLEMENTATION_REVIEW_2026-08-05.md).
- CR-B runtime loop, presentation truth and review evidence: [CR_B_RUNTIME_IMPLEMENTATION_REVIEW_2026-08-05.md](CR_B_RUNTIME_IMPLEMENTATION_REVIEW_2026-08-05.md).
- WorkProgress v2 and AB-B runtime foundation review/evidence: [AB_B_WORK_PROGRESS_IMPLEMENTATION_REVIEW_2026-08-05.md](AB_B_WORK_PROGRESS_IMPLEMENTATION_REVIEW_2026-08-05.md).
- Frozen P2 real Agent/Harness interface execution contract: [P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md](roadmap/P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md).
- Formal P3alpha backend Core/Store/Executor/policy review and evidence: [P3ALPHA_REPLACEMENT_REVIEW_2026-08-05.md](P3ALPHA_REPLACEMENT_REVIEW_2026-08-05.md).
- V0 immutable evidence: [V0_20260802_ee2896a4.md](evidence/V0_20260802_ee2896a4.md).
- Environment and operating procedures: [E2E_RUNBOOK.md](runbooks/E2E_RUNBOOK.md).

## Next actions

1. Build the next P3alpha acceptance slice around the reviewed backend: obtain a real authenticated principal and server-resolved authorization/context, compose policy/Core/Store/ED with startup and periodic reconciliation plus route telemetry, and close ED workspace isolation. Keep VB-C, TC-C and WorkProgress/CR return wiring as explicit later work.
2. Keep Speech critical-token safety as the next independent P1 slice; it must gate committed input with zero Agent/Tool/Task side effects before clarification, without taking Task authority from VB-B/TC-B.
3. Resume Worker2 against D-059 and the frozen P2 interface Task Packet; connect CR-B/AB-B only through its reviewed real Agent/Harness source, exact cancel, formal history and atomic composition seams. Connect AIO-B only through owned SR/RM B/C packages. These bounded foundations are not the formal P1/P2 end-to-end routes.
