# Live Voice current status

> Updated: 2026-08-05
> This is the only mutable source for current branch facts, milestones, track state, blockers and next actions. Detailed tests, reviews and immutable evidence are linked rather than copied here.

## Git and release identity

- Development branch: `hx/0803_live_voice`; upstream: `origin/hx/0803_live_voice`.
- Current verified implementation base: `56b45480d8ef05199a00cbcb100d499557871035`, exactly even with upstream when this D-031 candidate started. The project-bound correction and closure documentation belong to the D-031 change batch; always verify Git at resume for its landed state rather than inferring it from this base.
- The Web Alpha/D-055 documentation reconciliation and delivery matrix form one documentation-only batch. Verify Git to determine whether that batch is committed or still local; do not discard, rewrite, commit or push later changes without the applicable user instruction and Git approval.
- Week 1 implementation is complete: corrected W1-K1 `857d5c06`, route telemetry `ac608738`, execution policy `f12a790b`, A packages `56450bdf`, and W1-X2/P1B `ad02fa6f` are committed in this branch history.
- D-031 monitor and zero-effect result gate are committed in `617fe256`. The project-bound Code Agent batch makes target/execution/artifact facts coherent, completed its affected automated matrix and D-053 reviews, and passed the accepted isolated real-service run. D-031 is `CLOSED` for its bounded Compatibility Adapter scope under D-057.
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
| P3alpha Task | TC/ED/VB A packages and fake vertical are committed; D-031's reviewed project-bound compatibility carrier passed its accepted real-service closure run | resume formal TC/ED/VB replacement | compatibility carrier still has no restart recovery, production authorization or formal TaskEvent authority |
| Integration | three fake verticals and opt-in Browser P1 fallback exist | after one real route passes review, start cumulative integration and service validation | Integrated mode is documented but not runnable |

V0 and task compatibility code remains fallback, `demo_substitute` or Compatibility Adapter under D-047. Do not add formal authority to `useLiveVoiceDemo`, the frontend TaskBridge or legacy `schedule.*`/JSON state. CR/TC/ED and the target modules must take ownership through incremental replacement.

## D-031 current state

The minimal monitor is complete for its approved boundary: one page-memory task, one in-flight status read, same-page exact-key reconciliation, strict task/target/provenance checks, bounded retry, truthful card state, no Chat mutation and at-most-once safe terminal speech. Exact automated results and three review passes are in the [D-031 implementation review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md).

The clean `d031-05` run proved unconfirmed zero mutation, exactly one run/task, same-task polling, terminal failure adoption, polling stop and zero-effective-change rejection. It also proved the former product defect:

- Web authorization and result validation use the selected JiuwenSwarm project;
- `extended_evolve_pipeline` executes configured Agent Core and promotes a private runtime extension;
- therefore a task can truthfully finish in the executor while failing the promised selected-project code result.

D-056 chooses **project-bound code execution** for the current candidate. Live Voice now requests fixed `project_code_pipeline` in Code Agent mode. Before task creation, the backend requires the selected persisted-session project, Code Agent root and Git top-level root to match exactly; it then persists the effective root, artifact kind, executor, pipeline and effect policy as trusted provenance. A mismatch, invalid Git target or explicit requirement to run tests, shell or Git commands returns a stable preflight error with zero task creation/trigger.

The background task runs in a fresh, non-reused `sched_*` Session without Chat history, memory, A2UI or user interaction, and the dedicated Session is cleaned on every exit. Its ability set is reduced to the project-scoped read/search/write/edit file tools; task/subagent, cron, send-file, search, skill, terminal and other configured abilities are removed. Task-local policy also disables every JiuwenSwarm/OpenJiuwen shell entry point, so tests, scripts, Git and remote commands cannot run; ordinary interactive and non-Live-Voice AutoHarness work retains its prior tool behavior. New tasks require the complete execution contract, while a tracked legacy task with no contract remains observable/cancellable but cannot satisfy monitor success evidence. The existing Git-visible result gate still rejects zero, ignored-only and foreign-root-only effects. Exact automated and review evidence belongs in the [D-031 implementation review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md).

The isolated project-bound run is recorded in [sanitized evidence](evidence/D031_20260805_PROJECT_BOUND.md). One committed-final command used command `lv-3635c613-d033-4834-bb41-e275c171ca91`, task `sch_592b8579` and execution `exec_4a99d01d`; it persisted the exact D-056 contract, appended `验证通过` to the selected target's `README.md`, kept target HEAD unchanged, reached `success/success`, and stopped polling after terminal adoption. A 15-second response timeout caused exact-key reconciliation and a second same-key `schedule.run` wire attempt, but the store contains one create command, one task and one execution.

D-057 accepts that result as D-031 `CLOSED` for the current Compatibility Adapter boundary. Startup task details were spoken; terminal completion speech was observed zero times, which is allowed by the current safe at-most-once—not guaranteed-delivery—contract. The target's `.gitignore`, `coding_memory/`, `prompt_attachment/` and ignored `.agent_history/` support paths are recorded rather than hidden; their placement belongs to the Agent Runtime/workspace-isolation follow-up. Earlier `radi.nd` output followed an incorrect committed ASR transcript and belongs to Speech fidelity. These ownership decisions do not grant formal TC/ED/VB authority or replacement credit.

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

- D-031's bounded validation is complete. Shared Code Agent runtime files currently land inside the selected project; Agent Runtime/workspace isolation must relocate or explicitly govern `.gitignore`, `coding_memory/`, `prompt_attachment/` and `.agent_history/` before a formal clean-workspace Gate can pass.
- D-031 terminal audio is safe at most once and may be skipped when no immediate safe gap exists; guaranteed/eventual terminal notification remains unimplemented.
- No real streaming Speech Provider, Browser↔Gateway media transport, browser Audio I/O evidence baseline, deployed secure origin or exact Web Alpha browser range is selected in Git.
- Integrated cumulative mode is not implemented. Current V0, stable-sentence and task modes remain separate compatibility/Demo routes.
- Browser Speech fidelity remains weak for critical Chinese and technical tokens; committed text and critical-token clarification remain required.
- Existing task scope is single-user request consistency, not production authorization; JSON guarantees are same-process, not exactly-once.
- Current supplement/cancel behavior is not a production generation or Agent/Tool side-effect fence.
- The repository-local `.venv` is absent. Frontend dependencies were restored from the lockfile for this candidate, and backend verification used the compatible neighboring `jiuwenswarm pr/.venv`; these are machine-local facts, not Git-restored guarantees.

## Detailed evidence routes

- Week 1 implementation and review: [W1-K1](W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md), [A packages](W1_A_PACKAGE_REVIEW_2026-08-04.md), [W1-X2/P1B](W1_X2_P1B_REVIEW_2026-08-04.md).
- D-031 review and sanitized real-service evidence: [implementation review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md), [project-bound closure run](evidence/D031_20260805_PROJECT_BOUND.md).
- V0 immutable evidence: [V0_20260802_ee2896a4.md](evidence/V0_20260802_ee2896a4.md).
- Environment and operating procedures: [E2E_RUNBOOK.md](runbooks/E2E_RUNBOOK.md).

## Next actions

1. Implement the first real P2 Agent compatibility route, then resume formal TC/ED/VB replacement. Once the real route passes code review, stop and remind the user before cumulative service validation.
2. Track ASR critical-token fidelity under P1 Speech, shared project artifact placement under Agent Runtime/workspace isolation, and guaranteed terminal notification only if the product requires stronger than safe at-most-once delivery.
