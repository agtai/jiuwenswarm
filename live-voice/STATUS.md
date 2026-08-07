# Live Voice current status

> Updated: 2026-08-07
> This is the only mutable source for current branch facts, milestones, track state, blockers and next actions. Detailed tests, reviews and immutable evidence are linked rather than copied here.

## Resume capsule

- Milestones: V0 `CLOSED`; Week 1 `CLOSED`; D-031 Compatibility Adapter `CLOSED`.
- Product Gate: Integrated Demo `NOT RUNNABLE`; Replacement Ledger `0/100`.
- Routes: P1 `fallback + reviewed AIO/batch-Speech + bounded Media/browser-transport activation owners, still unavailable at the product registry`; P2 `default-off stock-Web committed-text submission into the real AgentManager/Harness/CR path + exact final-presentation acknowledgement/history`; P3alpha `default-off authenticated query/progress + bounded trusted confirmation and create/cancel mutation, formal voice fail-closed`; X-OBS `correlation + retained lifecycle + deterministic fault harness, not registered`; Integrated `default-off Web→Gateway→AgentServer P2/P3alpha text path, without a real P1/Provider, X-OBS backend or acceptance journey`.
- Current priority: treat the reviewed Wave A+B implementation as source-complete at tested code `dd637e60`, preserve its [frozen execution packet](roadmap/ALPHA_WAVE_AB_EXECUTION_2026-08-07.md) and [integration review](ALPHA_WAVE_AB_INTEGRATION_REVIEW_2026-08-07.md), and prepare only dependency-backed Wave C work: real Provider/media deployment and zero-persistence evidence, X-OBS exporter/backend, disposable registered Code project and real desktop-Chrome/service journeys.
- The previous D-060 integration batch is part of pushed `hx/0803_live_voice` at `7876e1ae`; its exact tested implementation remains `0ef0f862` and its documentation commit is `7876e1ae`. The reviewed local `codex/lv-alpha-ab-integration` candidate was created from that exact pushed baseline and has tested code at `dd637e604939cef7200d4ff5d30acf55a89d62f2`. On explicit user instruction, local `hx/0803_live_voice` was fast-forwarded to the reviewed candidate documentation HEAD; its upstream remains at `7876e1ae`, so the local branch is eight commits ahead and no Wave A+B commit was pushed. Resolve the amendable documentation HEAD dynamically rather than copying it here. No real browser/device/Provider/deployed-service E2E or cumulative acceptance Gate has run, and Replacement Ledger credit remains zero.

## Package state capsule

- `CLOSED`: shared ACG/telemetry kernel, every P1/P2/P3alpha A package, deterministic fake verticals, Browser P1 fallback and bounded D-031 Compatibility Adapter.
- `FOUNDATION ONLY`: the cross-language Gate, ProductAuthority, Browser↔Gateway media seam, progress-return bridge and bounded composition-root/Media/X-OBS packages are source-integrated. Media has bounded startup/close ownership and X-OBS has a deterministic fault harness, but both remain unavailable or unregistered at the product route and earn no Replacement Ledger credit.
- `PARTIAL / STILL OPEN`: tested implementation `dd637e60` owns default-off stock-Web P2 committed-text submission, retained output/presentation acknowledgement, exact Agent history, P3 trusted confirmation/create/cancel mutation, route recovery and bounded replay state. Production identity, P3 voice handoff, registered real Media/Provider, X-OBS registration/backend and real browser/device/service evidence remain open.
- `CROSS-CUTTING PARTIAL`: P2/P3alpha now form a real source-level Web→Gateway→AgentServer→Agent/Task text path with fail-closed limits and cleanup. It is not a cumulative real P1/P2/P3alpha journey, and the single P2 runtime intentionally admits at most 256 committed turns with no stock-Web automatic rollover.

## Git and release identity

- Development upstream `agtai/hx/0803_live_voice` remains at latest pushed commit `7876e1ae9caad28535abcc674d6b02f72553fe4f`. Local `hx/0803_live_voice` now contains the reviewed Wave A+B candidate through the current documentation HEAD, eight commits ahead of its upstream after an explicit local fast-forward; `codex/lv-alpha-ab-integration` remains the exact no-upstream candidate pointer. Resolve current HEAD and dirty state dynamically at resume.
- The six product-foundation feats run from formal batch Speech `c85979bd` through the cumulative Web shell `19dadc13`. The subsequent bounded P1/P2/P3alpha/X-OBS commits `72023158`, `16243d26`, `b8dbb9c4` and `afec02ce` are linearly integrated on the branch; this is source integration, not product-route closure.
- The reviewed Gate-0/Authority/Media/Progress batch is linearly integrated as `a7b2a939`, `be9374cc`, `214a3139` and `5d599c54`; the composition-root/P2/P3/X-OBS/Media package batch is integrated as `9adcc4cc`; the central AgentServer registration and P2/P3 product-wiring batch is integrated as `f742fac0`.
- D-060 governance is `b0ecd021`; the first Alpha integration batch is `ebb4f432` (stock Web/Gateway/AgentServer), `8aa59906` (P2 lifecycle), `cb88f5bb` (P3 durable outbox), `9724149b` (Media frame/payload ownership) and tested implementation `0ef0f862` (X-OBS lifecycle), with documentation recorded by pushed commit `7876e1ae`. These are reviewed source integrations, not Alpha acceptance.
- Wave A+B is locally integrated after `7876e1ae` as `c187b38d` (execution start), `a2ac5772` (trusted P3 confirmation), `e42878aa` (X-OBS fault harness), `b1361572` (Media activation ownership), `913bb3f2` + `5005aecf` (retained P2 submit/presentation acknowledgement) and tested integration code `dd637e60`. Exact source commits, review fixes and verification are frozen in the [Wave A+B integration review](ALPHA_WAVE_AB_INTEGRATION_REVIEW_2026-08-07.md); this local range is unpushed and is not Alpha acceptance.
- Reviewed foundations are reconciled as AIO-B `e407af45` → `50b98b4a`, CR-B `4b384970` → `1d721ca0`, and AB-B `a7ec6bad` → `3d357c2e`; their review records own the exact fixes and verification.
- V0 immutable Released/Frozen baseline: `ee2896a4afb186e693c720476b6de10797e66f72`, Gate 0–6 PASS.

Git source and tests are the implementation fact. If Git and this file disagree, report the gap and repair this file rather than following stale prose.

## Accepted product target and schedule meaning

D-046 defines one cumulative engineering route and D-055 makes the current product carrier **Integrated Web Alpha**:

1. **V0 — complete and frozen:** real microphone → committed transcript → real JiuwenSwarm Agent/Tool → truthful final → speech.
2. **W2 — cumulative Integrated Demo Gate:** P1, P2, P3alpha, Context, Progress, Failure/Degradation and Observability run in one product path and reach at least 90/100 with mandatory invariants.
3. **W3/W4 — Integrated Web Alpha Gate:** real P1/P2/P3alpha verticals, desktop Web platform evidence and the joint non-blocking interaction/progress Gate pass on one immutable candidate.
4. **Later:** complete P3, D1/D2, production authorization, wider browsers/platforms, operational SLOs, privacy/retention and release hardening.

`W2/W3/W4` are dependency and delivery-order windows, not current calendar promises. D-060 is the active bounded exception to D-052: four non-overlapping implementation Sessions run under one Main Integration Owner and one single-writer integration lease. D-061 runs one cumulative smoke after a complete reviewed cherry-pick batch rather than after every individual cherry-pick. These decisions change resource allocation, local Git procedure and validation cadence, not package truth, Alpha acceptance, production claims or calendar commitment. No replacement calendar estimate is accepted yet. The stable package map and historical one-engineer timeboxes are in the [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md); current ownership is in the [Alpha parallel execution plan](roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md).

The carrier is the JiuwenSwarm desktop Web frontend. D-058 freezes the first Alpha compatibility promise to one desktop Google Chrome baseline. Every candidate must still record exact Chrome/OS/origin/device/network facts; Chrome/Chromium 107 remains only the implementation floor. Edge, other Chromium builds, Firefox, Safari, mobile Web, PWA, WebView2 and native clients are outside the current Alpha promise. Deployed Alpha requires a secure context and Gateway-held Provider credentials.

## External planning-label mapping

- `Confirm the product scope and key technical choices` maps to the architecture/decision and X-WEB scope Gate. The current Alpha product scope, carrier, Chrome baseline and AIO choice are accepted; Speech Provider, media transport/codec and production deployment/auth choices remain package-owned open decisions, so the combined label is `PARTIAL` unless it means only the kickoff scope decision.
- `Build a production-ready voice flow` maps across W2/W4 P1/P2/X-E2E/X-WEB/X-OBS and the later Production hardening scope, with P3 included when background work is part of the journey. V0 proves only a demo-grade flow; this label remains `OPEN`.

## Current delivery dashboard

| Track | Current implementation fact | Next bounded work | Dependency / limit |
|---|---|---|---|
| Shared contract | ACG v2 critical kernel, fixtures/fakes/conformance and route telemetry are committed and reviewed; strict Python/TypeScript ContextRef and source-backed WorkProgress v2 parity are integrated | keep stable while real consumers integrate | ContextRef authorization/expiry/redaction enforcement remains consumer-owned; no replacement credit from contract/fake evidence alone |
| P1 Speech I/O | AIO/batch-Speech and exact LVM1 seams are committed; Media and browser transport now have bounded activation/startup, partial-failure cleanup, frame/payload ownership and idempotent close | prove a registered real route-to-disk zero-persistence boundary, select/configure Provider and transport, then wire and exercise capture/playout | `MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN`; central product registry still returns Media unavailable; no Provider/device/latency evidence or P1 credit |
| P2 Realtime | stock Web default-off activates an Alpha-authorized runtime, submits committed text once to the real AgentManager/Harness/CR path, retains exact notification/final state and ACKs exact presentation/history | run a real registered Agent/Tool browser journey and add a reviewed rollover design if sessions must exceed the bounded 256-turn runtime | no production identity, speech/media journey, real Agent/Tool E2E or P2/Web credit |
| P3alpha Task | stock Web authenticates query/progress, owns exact UI delivery ACK, issues a bounded trusted confirmation and performs exact create/cancel mutation with current-authority rechecks | add atomic voice handoff and validate against a disposable registered Code project/model/configuration | voice is `TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE`; bounded Alpha authority is not production authorization; UI ACK is not human observation |
| Integration / X-OBS | default-off Web→Gateway→AgentServer P2/P3alpha text routes, exact error propagation, reconnect fencing and cleanup are source-integrated; X-OBS has a bounded deterministic fault harness | register X-OBS only with truthful Composition state, add exporter/backend, then run real P1/P2/P3alpha vertical and joint journeys | X-OBS is not registered; no exporter/retention/SLO backend, secure Chrome/device/service journey or runnable Integrated Gate |

V0 and task compatibility code remains fallback, `demo_substitute` or Compatibility Adapter under D-047. Do not add formal authority to `useLiveVoiceDemo`, the frontend TaskBridge or legacy `schedule.*`/JSON state. CR/TC/ED and the target modules must take ownership through incremental replacement.

## D-031 current state

D-057 accepts D-031 as `CLOSED` for its bounded Compatibility Adapter scope: one page-memory task, one in-flight read, exact-key reconciliation, strict task/target/provenance checks, bounded retry, truthful terminal state, no Chat mutation and safe at-most-once terminal speech. It does not grant formal TC/ED/VB authority or replacement credit.

D-056 binds execution to the selected persisted project, Code Agent root and Git top-level. Each task uses a fresh restricted Session, rejects shell/test/Git requirements before creation, cleans up on every exit and requires a Git-visible selected-project effect. Mismatch, invalid target, zero effect, ignored-only effect and foreign-root-only effect fail closed.

The accepted isolated run proves that bounded contract and records its limitations. Exact commands, IDs, retry behavior, mutation, automated matrix and review passes remain in the [implementation review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md) and [sanitized evidence](evidence/D031_20260805_PROJECT_BOUND.md). Workspace support paths, eventual terminal notification and Speech fidelity remain follow-ups under their owning tracks.

## Demo Replacement Ledger

The [Integrated Demo acceptance](validation/INTEGRATED_DEMO_ACCEPTANCE.md) owns scoring. Current credit remains zero because no formal real route has completed its required acceptance evidence.

| Weighted journey | Weight | Current route | Credit | Formal replacement condition |
|---|---:|---|---:|---|
| P1 capture, recognition, synthesis, playout | 20 | Browser Speech/TTS fallback; formal Media remains registry-unavailable | 0 | AIO/SR/SS real Adapter evidence |
| P2 lifecycle, non-blocking work, fence/history | 40 | default-off formal text route is source-integrated; compatibility Chat remains available | 0 | CR/RM/II/AB real cumulative-route evidence |
| P3alpha create/control/events/progress | 25 | default-off formal query/progress/create/cancel source route; voice unavailable; D-031 remains a substitute | 0 | TC/ED/VB real Core/Event/Executor and voice-handoff evidence |
| Context, degradation, observability, flag-off | 15 | versioned route facts and deterministic fault harness; X-OBS backend unregistered | 0 | correlated real-path trace, exporter/backend and tested fallback |
| **Total** | **100** | scoring has not started | **0** | W2 requires at least 90 and every mandatory invariant |

## Execution and review policy

- D-060 supersedes D-052 only for the accepted current Alpha execution window. Four GPT/Sol implementation Sessions own P1, P2, P3alpha and cross-cutting leaf scopes; Main owns shared Authority/contracts, Web activation, central Composition, AgentServer/Gateway dispatch, cumulative evidence and final Gates. Exact file boundaries and handoff rules are frozen in the [Alpha parallel execution plan](roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md).
- One integration worktree has one writer. Main grants a lease naming source branch, commit, target and integration method. Semantic conflicts return to Main and the owning Session; integration glue is separately reviewed and retested.
- D-061 runs cumulative smoke once after the full reviewed cherry-pick batch; semantic conflict resolution or integration glue still receives affected checks before that final run.
- D-053 requires Tier 2/3 batches to complete self-review, cold complete-diff review and independent `/review` or a recorded equivalent. Tier 1 normally uses the first two unless risk is raised.
- Within D-060 scope, local stage/commit/amend/squash/rebase/merge/cherry-pick and local branch/ref/worktree operations no longer require per-operation user approval. Task Sessions may create their final commit only after review pass and may integrate only under a Main-issued lease. Any operation updating a remote ref, including normal/force push or remote branch/tag creation/update/deletion, still requires separate exact user approval; Task Sessions never push.

## Known blockers and machine-private conditions

- D-031's bounded validation is complete. Shared Code Agent runtime files currently land inside the selected project; Agent Runtime/workspace isolation must relocate or explicitly govern `.gitignore`, `coding_memory/`, `prompt_attachment/` and `.agent_history/` before a formal clean-workspace Gate can pass.
- D-031 terminal audio is safe at most once and may be skipped when no immediate safe gap exists; the new notification arbiter is not wired to D-031/CR, so guaranteed/eventual terminal notification remains unavailable in the product path.
- D-058 selects the single-desktop-Chrome range and AIO-B design. One controlled Chrome/default-microphone normal path passed, but permission revoke, device loss, background lifecycle and AIO-C latency still lack real evidence. Selected streaming Speech Provider, Browser↔Gateway media transport and deployed secure-origin evidence remain open.
- Integrated cumulative mode is still not runnable. Tested implementation `dd637e60` adds default-off committed P2 text submission/presentation history and bounded P3alpha confirmation/create/cancel on the real source path, but still has no product-registered Media/Provider, X-OBS backend, production identity or real browser/service Agent/Tool/task journey. Current V0, stable-sentence and task modes remain separate compatibility/Demo routes.
- Critical-token clarification and once-only dispatch are implemented and tested only as an unwired package. Browser Speech fidelity remains weak for critical Chinese and technical tokens, so no protected product path may bypass that Gate once composition begins.
- Existing task scope is single-user request consistency, not production authorization; JSON guarantees are same-process, not exactly-once.
- Current supplement/cancel behavior is not a production generation or Agent/Tool side-effect fence.
- D-059's real-Agent/Harness/CR foundation passed its three review equivalents after fixes, but remains product-level `PARTIAL` until authenticated composition and cumulative real browser/media/service evidence.
- `MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN`: the central registry explicitly returns Media unavailable. Bounded package/browser activation ownership and the binary seam are tested, but no registered real route-to-disk regression proves zero audio-payload persistence.
- The registered Authority source is the existing static P3 Alpha bearer plus server Session/Project registry. It is real for this bounded route but is not production identity, browser-user authentication or Provider authority.
- P3alpha query, text progress and bounded confirmation-backed create/cancel are centrally wired under explicit default-off Alpha flags. Production authorization and formal voice remain closed; voice still lacks an atomic TaskEvent/projection authority handoff.
- X-OBS has bounded export buffering, retained worker-lease cleanup and a deterministic saturation/timeout/late-result fault harness, but remains intentionally unregistered and has no product consumer, exporter transport, retention policy or SLO backend.
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
- Earlier bounded P1/P2/P3alpha/X-OBS foundations: `72023158`, `16243d26`, `b8dbb9c4`, `afec02ce`; [the repository-local index](LATEST_FOUNDATIONS_D053_REVIEW_2026-08-06.md) records exact SHA/ancestry/file scope and retained task-evidence limits without overstating independent D-053 acceptance.
- Product composition sequencing, evidence vocabulary and cumulative smoke contract: [Gate-0 record](roadmap/PRODUCT_COMPOSITION_GATE_0_2026-08-06.md).
- Composition root and bounded P2/P3/X-OBS/Media package review for `9adcc4cc`: [product-composition foundations review](PRODUCT_COMPOSITION_FOUNDATIONS_REVIEW_2026-08-06.md).
- Default-off AgentServer registration, Alpha Authority, P2/P3 wiring and D-053 review for `f742fac0`: [product-composition registration review](PRODUCT_COMPOSITION_REGISTRATION_REVIEW_2026-08-06.md).
- Stock-Web activation/acknowledgement, first four-lane hardening integration, D-053 closure and cumulative smoke for tested implementation `0ef0f862`, documented by pushed commit `7876e1ae`: [Alpha product integration review](ALPHA_PRODUCT_INTEGRATION_REVIEW_2026-08-07.md).
- Wave A+B P1/P2/P3alpha/X-OBS source commits, Main integration glue, D-053 closure, environment preflight and cumulative smoke for tested implementation `dd637e60`: [Alpha Wave A+B integration review](ALPHA_WAVE_AB_INTEGRATION_REVIEW_2026-08-07.md).
- Frozen Wave A+B seven-role execution, oracle, handoff and smoke-recovery contract: [Wave A+B execution packet](roadmap/ALPHA_WAVE_AB_EXECUTION_2026-08-07.md), the [Alpha parallel execution plan](roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md), D-060 and D-061.
- V0 immutable evidence: [V0_20260802_ee2896a4.md](evidence/V0_20260802_ee2896a4.md).
- Environment and operating procedures: [E2E_RUNBOOK.md](runbooks/E2E_RUNBOOK.md).

## Next actions

1. Supply real Speech Provider configuration/network and a secure deployed browser/device path, then prove the product-registered Media route-to-disk zero-persistence boundary before enabling P1.
2. Supply an X-OBS exporter/backend with retention/SLO policy and reconcile truthful Composition registration; do not substitute the deterministic fault harness for a backend.
3. Register a disposable Code project with real model/configuration and validate P3alpha create/cancel/progress plus the remaining atomic voice-handoff design; retain the 256-turn P2 runtime limit until a reviewed rollover owner exists.
4. Run real P1/P2/P3alpha verticals, the joint desktop-Chrome/service E2E and the Immutable Alpha Gate on one candidate before changing the `0/100` ledger or any Gate state.
