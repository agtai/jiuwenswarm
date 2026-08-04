# Live Voice current status

> Updated: 2026-08-05
> This is the only mutable source for current branch facts, milestones, track state, blockers and next actions. Detailed tests, reviews and immutable evidence are linked rather than copied here.

## Git and release identity

- Development branch: `hx/0803_live_voice`; upstream: `agtai/hx/0803_live_voice`.
- Documentation-audit implementation base: `617fe256db05b07a07b6d457b15f07c02d17d9bf`; at the 2026-08-05 audit it was two commits ahead of upstream. The exact current HEAD and working-tree state are intentionally not duplicated here; always verify Git at resume.
- The Web Alpha/D-055 documentation reconciliation and delivery matrix form one documentation-only batch. Verify Git to determine whether that batch is committed or still local; do not discard, rewrite, commit or push later changes without the applicable user instruction and Git approval.
- Week 1 implementation is complete: corrected W1-K1 `857d5c06`, route telemetry `ac608738`, execution policy `f12a790b`, A packages `56450bdf`, and W1-X2/P1B `ad02fa6f` are committed in this branch history.
- D-031 monitor and zero-effect result gate are committed in `617fe256`; D-031 remains `PARTIAL` because its real execution target/artifact contract is not coherent.
- V0 immutable Released/Frozen baseline: `ee2896a4afb186e693c720476b6de10797e66f72`, Gate 0–6 PASS.

Git source and tests are the implementation fact. If Git and this file disagree, report the gap and repair this file rather than following stale prose.

## Accepted product target and schedule meaning

D-046 defines one cumulative engineering route and D-055 makes the current product carrier **Integrated Web Alpha**:

1. **V0 — complete and frozen:** real microphone → committed transcript → real JiuwenSwarm Agent/Tool → truthful final → speech.
2. **W2 — cumulative Integrated Demo Gate:** P1, P2, P3alpha, Context, Progress, Failure/Degradation and Observability run in one product path and reach at least 90/100 with mandatory invariants.
3. **W3/W4 — Integrated Web Alpha Gate:** real P1/P2/P3alpha verticals, desktop Web platform evidence and the joint non-blocking interaction/progress Gate pass on one immutable candidate.
4. **Later:** complete P3, D1/D2, production authorization, wider browsers/platforms, operational SLOs, privacy/retention and release hardening.

`W2/W3/W4` are dependency and delivery-order windows, not current calendar promises. The original three-to-four-week estimate assumed at least three useful implementation lanes. D-052 now fixes one GPT/Sol lane, so no replacement calendar estimate is accepted yet. The stable package map and historical one-engineer timeboxes are in the [Web Alpha delivery matrix](roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md).

The carrier is the JiuwenSwarm desktop Web frontend. Deployed Alpha requires a secure context and Gateway-held Provider credentials. X-WEB must still choose the exact desktop Chromium acceptance range. Chrome/Chromium 107 is the frontend implementation compatibility floor, not by itself the Web Alpha evidence baseline or a Chrome+Edge promise.

## Current delivery dashboard

| Track | Current implementation fact | Next bounded work | Dependency / limit |
|---|---|---|---|
| Shared contract | ACG v2 critical kernel, fixtures/fakes/conformance and route telemetry are committed and reviewed | keep stable while real consumers integrate | no replacement credit from contract/fake evidence alone |
| P1 Speech I/O | AIO/SR/SS Ports and Browser Speech compatibility fallback are committed | plan browser AIO and selected real Speech Provider B/C paths | Provider, browser/device and real audio evidence are not selected |
| P2 Realtime | CR/RM/II/AB A packages and deterministic fake vertical are committed | implement the first real Agent compatibility path | no real media transport, canonical runtime loop or Agent WorkProgress route yet |
| P3alpha Task | TC/ED/VB A packages, fake vertical and D-031 monitor are committed | resolve D-031 execution contract, then implement project-bound Executor/Harness preflight and Adapter | no positive real task before target/execution/artifact facts agree |
| Integration | three fake verticals and opt-in Browser P1 fallback exist | after one real route passes review, start cumulative integration and service validation | Integrated mode is documented but not runnable |

V0 and task compatibility code remains fallback, `demo_substitute` or Compatibility Adapter under D-047. Do not add formal authority to `useLiveVoiceDemo`, the frontend TaskBridge or legacy `schedule.*`/JSON state. CR/TC/ED and the target modules must take ownership through incremental replacement.

## D-031 current state and required choice

The minimal monitor is complete for its approved boundary: one page-memory task, one in-flight status read, same-page exact-key reconciliation, strict task/target/provenance checks, bounded retry, truthful card state, no Chat mutation and at-most-once safe terminal speech. Exact automated results and three review passes are in the [D-031 implementation review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md).

The clean `d031-05` run proved unconfirmed zero mutation, exactly one run/task, same-task polling, terminal failure adoption, polling stop and zero-effective-change rejection. It also proved the remaining product defect:

- Web authorization and result validation use the selected JiuwenSwarm project;
- `extended_evolve_pipeline` executes configured Agent Core and promotes a private runtime extension;
- therefore a task can truthfully finish in the executor while failing the promised selected-project code result.

Before changing code, choose one coherent meaning:

1. **Project-bound code execution — recommended:** the selected project is the effective execution root and the expected artifact is a project code change.
2. **Explicit runtime-extension Demo:** rename and restrict the command to runtime-extension creation and validate that artifact instead; it does not satisfy a general “后台代码优化任务”.

Do not apply a one-field `repo_url` patch. Resolve effective execution root, pipeline and artifact kind in a bounded backend preflight, expose them as provenance, and reject any mismatch before model, clone, extension or selected-project side effects. Do not run another positive real task until this is implemented and reviewed.

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
- D-053 requires Tier 2/3 batches to complete self-review, cold complete-diff review and independent `/review` or a recorded equivalent. Tier 1 normally uses the first two unless risk is raised.
- Related files in one coherent boundary may share review and commit. Every commit and push still requires separate exact approval under root `AGENTS.md`.

## Known blockers and machine-private conditions

- D-031 mixes selected-project validation with configured-Agent-Core execution; positive real task validation is blocked.
- No real streaming Speech Provider, Browser↔Gateway media transport, browser Audio I/O evidence baseline, deployed secure origin or exact Web Alpha browser range is selected in Git.
- Integrated cumulative mode is not implemented. Current V0, stable-sentence and task modes remain separate compatibility/Demo routes.
- Browser Speech fidelity remains weak for critical Chinese and technical tokens; committed text and critical-token clarification remain required.
- Existing task scope is single-user request consistency, not production authorization; JSON guarantees are same-process, not exactly-once.
- Current supplement/cancel behavior is not a production generation or Agent/Tool side-effect fence.
- The repository `.venv` and frontend dependencies are available in this worktree, but credentials, Provider configuration, project registration, runtime data, browser permissions/devices and network state remain machine-private.

## Detailed evidence routes

- Week 1 implementation and review: [W1-K1](W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md), [A packages](W1_A_PACKAGE_REVIEW_2026-08-04.md), [W1-X2/P1B](W1_X2_P1B_REVIEW_2026-08-04.md).
- D-031 automated and real-service evidence: [D031_IMPLEMENTATION_REVIEW_2026-08-04.md](D031_IMPLEMENTATION_REVIEW_2026-08-04.md).
- V0 immutable evidence: [V0_20260802_ee2896a4.md](evidence/V0_20260802_ee2896a4.md).
- Environment and operating procedures: [E2E_RUNBOOK.md](runbooks/E2E_RUNBOOK.md).

## Next actions

1. Confirm the D-031 product meaning: project-bound code execution is recommended; runtime-extension Demo is the explicit alternative.
2. Implement the backend preflight and project-bound Executor/Harness Adapter without expanding the monitor or TaskBridge into execution authority.
3. Run the D-031 automated matrix and three reviews, then perform one short isolated real-service validation covering semantic target output, zero forbidden effects, truthful terminal status, polling stop and at-most-once speech.
4. Keep the resulting D-031 code uncommitted until that validation is complete; then report scope/diff/tests/exclusions and request commit approval. The separately authorized documentation-only batch does not authorize a D-031 code commit or any push; request push approval separately.
5. After D-031, implement the first real P2 Agent compatibility route. Once it passes code review, stop and remind the user before starting cumulative service validation.
