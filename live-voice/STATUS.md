# Live Voice current status

> Updated: 2026-08-06
> This is the only mutable source for current branch facts, milestones, track state, blockers and next actions. Detailed tests, reviews and immutable evidence are linked rather than copied here.

## Resume capsule

- Milestones: V0 `CLOSED`; Week 1 `CLOSED`; D-031 Compatibility Adapter `CLOSED`.
- Product Gate: Integrated Demo `NOT RUNNABLE`; Replacement Ledger `0/100`.
- Routes: P1 `fallback + reviewed AIO/batch-Speech + contract-only Browser↔Gateway media seam`; P2 `default-off central Alpha-authorized activation into real AgentManager/runtime/interaction, no TurnCommit product caller`; P3alpha `default-off central authenticated read-only query + exact live text-progress subscription/Web consumer, mutation and formal voice fail-closed`; X-OBS `correlation + bounded export-buffer foundation, not registered`; Integrated `default-off AgentServer registry + Web/Gateway RPC boundary, no cumulative real journey`.
- Current priority: supply a safe stock-Web activation/auth owner and a committed P2 TurnCommit/PresentationAck caller, then prove one AgentServer→Gateway→Web progress event end to end. Provider/Media, II, P3 confirmation/voice handoff, X-OBS lifecycle/backend and real Chrome/service evidence remain separate open work.
- Committed and pushed HEAD `9adcc4cc` contains the reviewed default-off composition root and bounded P2/P3/X-OBS/Media package Adapters. The current uncommitted candidate adds the central AgentServer registration plus real Alpha Authority, P2 runtime/interaction, P3 query/subscription and authenticated text/UI progress wiring. Final verification passed `422` focused Python tests, `95` shared/fake-vertical tests and `154` Web/legacy-Demo tests plus affected static checks. This is source integration only; no real browser/device/Provider/service or cumulative acceptance Gate ran, and Replacement Ledger credit remains zero.

## Package state capsule

- `CLOSED`: shared ACG/telemetry kernel, every P1/P2/P3alpha A package, deterministic fake verticals, Browser P1 fallback and bounded D-031 Compatibility Adapter.
- `FOUNDATION ONLY`: the cross-language Gate, ProductAuthority, Browser↔Gateway media seam, progress-return bridge and the bounded composition-root/P2/P3/X-OBS/Media package Adapters are committed through `9adcc4cc`. X-OBS and Media remain package-only/unavailable and none of this evidence earns Replacement Ledger credit.
- `PARTIAL / STILL OPEN`: the current candidate centrally registers only Alpha Authority, P2 activation, P3 read-only query and text progress. Stock-Web activation/token ownership, P2 TurnCommit/PresentationAck, a full Gateway/Web delivery acknowledgement, production identity, P3 confirmation/voice handoff, X-OBS lifecycle/backend, registered Media route-to-disk zero-persistence evidence and real browser/device/Provider/service evidence remain open.
- `CROSS-CUTTING PARTIAL`: X-OBS now has correlated Python/TypeScript facts plus bounded buffering, and X-E2E/X-WEB has a guarded diagnostics/composition shell; no exporter consumer/backend or cumulative real journey is wired.

## Git and release identity

- Development branch: `hx/0803_live_voice`; configured upstream: `agtai/hx/0803_live_voice`. Current committed HEAD is `9adcc4cc`; resolve HEAD, divergence and dirty state dynamically at resume.
- The six product-foundation feats run from formal batch Speech `c85979bd` through the cumulative Web shell `19dadc13`. The subsequent bounded P1/P2/P3alpha/X-OBS commits `72023158`, `16243d26`, `b8dbb9c4` and `afec02ce` are linearly integrated on the branch; this is source integration, not product-route closure.
- The reviewed Gate-0/Authority/Media/Progress batch is linearly integrated as `a7b2a939`, `be9374cc`, `214a3139` and `5d599c54`; the composition-root/P2/P3/X-OBS/Media package batch is integrated as `9adcc4cc`. The current central-registration candidate remains uncommitted.
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
| P1 Speech I/O | AIO/batch-Speech and the exact LVM1 media seam are committed; central composition reports Media unavailable | prove a registered real route-to-disk zero-persistence boundary, select/configure the Provider, then wire capture/playout | `MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN`; no Provider/device/latency evidence or P1 credit |
| P2 Realtime | the default-off registry resolves Alpha Authority before real AgentManager allocation and opens retained runtime/interaction leases | add the stock product caller for committed TurnCommit, PresentationAck/history and the real Agent/media journey | no production identity, TurnCommit dispatch, Agent/Tool journey or P2/Web credit |
| P3alpha Task | read-only P3 queries and exact live TaskEvent→authenticated text/UI progress are centrally wired behind default-off flags | add safe Web activation/token ownership and one full Gateway/Web delivery acknowledgement; separately supply trusted confirmation and atomic voice handoff | mutation remains closed; voice is `TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE`; socket write is not UI acknowledgement |
| Integration / X-OBS | AgentServer now owns the default-off Authority-first registry, Gateway RPC forwarding and cleanup order; fallback/Demo routes remain separate | resolve X-OBS nonformal-route/worker-lease lifetime, then wire exporter/backend and run the cumulative real journey | X-OBS is not registered; no exporter/retention/SLO backend, Chrome/device/service journey or runnable Integrated Gate |

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
- Integrated cumulative mode is not implemented. The current uncommitted candidate adds a default-off central registry and bounded real server-side P2/P3 paths, but the stock Web product has no safe activation/token owner and no full Agent/Tool/media/progress journey. Current V0, stable-sentence and task modes remain separate compatibility/Demo routes.
- Critical-token clarification and once-only dispatch are implemented and tested only as an unwired package. Browser Speech fidelity remains weak for critical Chinese and technical tokens, so no protected product path may bypass that Gate once composition begins.
- Existing task scope is single-user request consistency, not production authorization; JSON guarantees are same-process, not exactly-once.
- Current supplement/cancel behavior is not a production generation or Agent/Tool side-effect fence.
- D-059's real-Agent/Harness/CR foundation passed its three review equivalents after fixes, but remains product-level `PARTIAL` until authenticated composition and cumulative real browser/media/service evidence.
- `MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN`: the central registry explicitly returns Media unavailable. The Vite JSON boundary and package binary seam are tested, but no registered real route-to-disk regression proves zero audio-payload persistence.
- The registered Authority source is the existing static P3 Alpha bearer plus server Session/Project registry. It is real for this bounded route but is not production identity, browser-user authentication or Provider authority.
- P3alpha read-only query and text progress are centrally wired, but production mutation remains closed because no trusted confirmation issuer exists. Formal voice remains closed because no atomic TaskEvent/projection authority handoff exists.
- X-OBS has bounded export buffering but is intentionally not registered because nonformal route truth is incompatible with its worker-lease lifetime. It also lacks a product consumer, exporter transport, retention policy and SLO backend.
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
- Current default-off AgentServer registration, Alpha Authority, P2/P3 wiring and D-053 review: [product-composition registration review](PRODUCT_COMPOSITION_REGISTRATION_REVIEW_2026-08-06.md).
- V0 immutable evidence: [V0_20260802_ee2896a4.md](evidence/V0_20260802_ee2896a4.md).
- Environment and operating procedures: [E2E_RUNBOOK.md](runbooks/E2E_RUNBOOK.md).

## Next actions

1. Review the current uncommitted registration candidate and request exact commit approval only after scope/message are agreed; keep Media unavailable and X-OBS unregistered.
2. Add a safe stock-Web activation/token owner and a P2 committed TurnCommit/PresentationAck caller, then prove AgentServer→Gateway→Web text progress with an observable UI delivery acknowledgement.
3. In parallel within frozen ownership, select/configure the Speech Provider and prove the dedicated Media route-to-disk boundary; complete II, trusted confirmation/voice handoff and the X-OBS lifecycle/backend boundary.
4. Run one real desktop-Chrome/service journey covering microphone/playout, Provider, JiuwenSwarm Agent/Tool, project Task, exact cancel, PresentationAck/history, restart/reconciliation, exporter evidence and secure deployment before changing the `0/100` ledger or any Gate state.
