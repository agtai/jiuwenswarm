# Live Voice current status

> Updated: 2026-08-05
> This is the only mutable source for current branch facts, milestones, track state, blockers, and next actions. Detailed design reviews and immutable evidence are linked rather than copied here.

## Git and release identity

- Development branch: `hx/0803_live_voice`.
- Upstream: `agtai/hx/0803_live_voice`.
- Corrected W1-K1 is committed as `857d5c06`; W1-X1 route telemetry is committed as `ac608738`; execution-policy documentation is committed as `f12a790b`.
- The P1A/P2A/P3A implementation is committed as `56450bdf`.
- The D-031 monitor and zero-effect result gate are committed locally as `d84fd388`; acceptance remains partial because the selected project is not yet the AutoHarness execution repository.
- Runtime implementation baseline reviewed by this consolidated planning record: `ac988b85e8a21eb4f378086bab58dac6a4d55d82`. Subsequent commits through the consolidated planning commit change documentation only. The planning commit intentionally does not self-record its SHA—verify actual HEAD and upstream at every resume.
- V0 immutable Released / Frozen baseline: `ee2896a4afb186e693c720476b6de10797e66f72` with Gate 0–6 PASS.
- Post-V0 foundation is integrated but remains partial; it is not formal P1/P2/P3alpha closure.
- D-052 governs current execution: GPT/Sol is the only implementation and review lane; D-041/D-048/D-049 remain historical context and code-source evidence. D-050 fixes the shared safe-integer rule; D-051 records the direct-on-development-branch implementation path.
- The previous Sol design batch is preserved in [SOL_MODULE_PRE_REVIEWS_2026-08-03.md](SOL_MODULE_PRE_REVIEWS_2026-08-03.md). Its blank non-Sol result fields are not current progress claims.
- D-048's dated package boundaries remain in [WEEK_1_EXECUTION_PACKAGES_2026-08-03.md](roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md), but D-049 replaces its W1-K1 owner. Five non-Sol W1-K1 candidates were reviewed and not integrated; see [the implementation review record](W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md).

Git is the implementation fact. Refresh this section whenever HEAD, upstream relation, or working-tree state materially changes.

## Accepted product target

D-046 defines one cumulative engineering line:

1. **V0 — complete and frozen:** the first real microphone -> committed transcript -> real JiuwenSwarm Agent/Tool -> truthful final -> speech loop.
2. **Week 2 — Integrated Demo 90% Gate:** P1, P2, P3alpha, Context, Progress, Failure/Degradation, and Observability appear in one cumulative Demo; target modules replace at least 90 weighted points of the defined Demo journey. Formal, fallback, substitute, unsupported, and unknown routes remain visible and auditable.
3. **Week 3–4 — Integrated Windows Alpha:** P1 + P2 + P3alpha pass their real vertical slices and the joint non-blocking interaction/progress Gate. Full P3 is a stretch goal; P3alpha is the committed task scope.
4. **Later — Beta/RC/Production:** full P3 operations, D1/D2, production authentication/authorization, multi-platform compatibility, operational SLOs, privacy/retention, and release hardening are not silently pulled into the four-week Alpha.

The complete solution remains the architecture target. The four-week commitment is an integrated Alpha, not production completion.

## Current implementation facts

### V0: RELEASED / FROZEN

Verified facts and sanitized evidence are in [V0_20260802_ee2896a4.md](evidence/V0_20260802_ee2896a4.md). Post-V0 code is not part of that release claim.

### Post-V0 foundation: INTEGRATED / PARTIAL

The branch contains:

- Browser Speech/TTS-based V0 and conservative stable-sentence preview behind flags;
- task identity, target/provenance, same-process idempotency, strict exact-key reconciliation, schedule-backed operations, task card/client/adapter/Bridge, and focused tests;
- the committed W1-K1 Python/TypeScript v2 shared kernel, fixtures, and conformance tests;
- accepted architecture designs for ACG-1, CR-A, SR-A/SS-A, and TC-A.

The committed HEAD does not yet contain:

- formal Conversation Runtime, response/generation fence, presented ledger, or real Realtime Media;
- P1 Speech Ports with a selected real streaming Provider and Windows Audio I/O closure;
- formal Task Core/Event Store/Executor Port, `events` API, restart reconciliation, or production AuthorizationContext;
- a runnable cumulative Integrated Demo mode or Week 2/Week 4 acceptance evidence.

D-047 records the accepted code-scope audit: the current V0 and task foundations retain their necessary safety regressions but are frozen as fallback, Demo substitute, or Compatibility Adapter. Do not add formal authority or platform features to `useLiveVoiceDemo`, the frontend TaskBridge, or the legacy `schedule.*`/JSON path; CR/TC/ED and the other target modules must take ownership through incremental Integrated-route replacement rather than a separate cleanup rewrite.

### W1-K1 correction: COMMITTED / VERIFIED / W1-S1 CLOSED

DeepSeek's five rejected candidates remain historical reference only, ending at remote `agtai/hx/0803_live_voice_ds` commit `6ce74a4b5ad9a3ea6f5be044e7114315826f6baa`. No candidate was merged or cherry-picked.

The committed Sol implementation provides the v2 shared kernel, but a later independent review reproduced two P1 gaps: the dated TypeScript verification command/output path was inconsistent, and the identity registry did not enforce the ACG connection-epoch binding while assigning `round` a false turn parent. Amended commit `857d5c06` aligns Python, TypeScript, fixtures, tests, ACG, and the canonical npm verification command. D-050 large-integer rejection and fail-closed poisoned streams remain intentional. Corrected results are `77` Python and `25` TypeScript tests, Ruff, Prettier, production build, diff check, and Markdown links passing; final diff review found no additional actionable defect. Detailed history is in [W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md](W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md).

### W1-X1 route telemetry: COMMITTED / VERIFIED

Only the two bounded files from historical DeepSeek candidate `9a5663c6d3fe25143240717e7e2e5ec5f1a0dbe2` were selectively reused; its branch history and W1-K1 changes were not merged or cherry-picked. GPT/Sol corrected runtime-mutability of the route vocabulary, missing formal provider provenance, and missing reasons on non-formal routes. Commit `ac608738` passes strict planned compilation, `17` focused tests, Prettier, the production build, and final diff review. This remains Tier 1 instrumentation and carries no replacement credit.

### Week 1 A packages: COMMITTED / VERIFIED / W1-S2 CLOSED

The commit containing this status implements `W1-P1A`, `W1-P2A-CR`, `W1-P2A-PORTS`, `W1-P3A-TC`, and `W1-P3A-PORTS`. The bounded Port/fake behavior, negative side-effect checks, immutable-commit verification, and grouped review pass. Detailed boundaries, corrections, scenario evidence, and exclusions are in [the Week 1 A-package review](W1_A_PACKAGE_REVIEW_2026-08-04.md).

This candidate does not claim a real Speech Provider, media transport, Harness Adapter, persistent Task Store/outbox, production authorization, restart recovery, public API, Integrated route, or Demo replacement credit.

### W1-X2 and W1-P1B: COMMITTED / VERIFIED / THREE REVIEWS COMPLETE

The commit containing this status adds the three deterministic fake verticals and an opt-in Browser Speech P1 compatibility route. Focused backend/frontend tests, affected legacy regressions, and default-off plus flag-on production builds pass. The fakes remain an automated harness, and Browser Speech remains a visible fallback rather than a real Provider.

Self-review, cold complete-diff review, and an independent Codex `/review` are complete. The independent review found one whitespace-only Browser recognition callback defect; it was fixed, its regression test was added, affected suites and both production-build modes passed, and the final cold diff found no further actionable defect. Detailed corrections, commands, and exclusions are in [the W1-X2/P1B review](W1_X2_P1B_REVIEW_2026-08-04.md).

### D-031 minimal task monitor: PARTIAL / MONITOR AND FAIL-CLOSED VERIFIED / EXECUTION TARGET UNBOUND

The approved timeboxed Adapter is committed in `d84fd388`. It monitors one page-memory task with immediate scoped status reads, one in-flight request, connection pause plus exact-key same-page reconciliation, strict task/target/provenance checks, retry delays capped at 10 seconds, Bridge synchronization, truthful task-card states, and at-most-once safe terminal notification. It does not write Chat state or add durable/multi-task behavior.

Focused frontend suites, the schedule service/WebSocket suites, and default-off plus task-flag-on production builds pass. The primary “后台代码优化任务” grammar and spoken target markers are implemented while the old name remains compatible. The clean `d031-03` run led to Windows log-open, UTF-8 reverse-read, and truthful error fixes. The clean `d031-04` run exposed false success with zero target change; Live Voice one-time tasks now fail closed for unchanged, ignored-cache-only, unreadable, or invalid Git targets.

The `d031-05` real run verified unconfirmed zero mutation, exactly one run/task, 233 same-task status reads, terminal failure adoption, polling stop, and the new `NO_EFFECTIVE_TARGET_CHANGE` gate. It also proved the remaining blocker: the selected JiuwenSwarm project is used for authorization/result checking, but `extended_evolve_pipeline` still executes against configured Agent Core and promotes a runtime extension under the private data directory. ASR had minor wording drift but the assess stage recovered the intended single-file/no-test/no-commit/no-push request; ASR was not causal. Do not repeat a positive real task until the execution/artifact contract is chosen and mismatches fail before model or repository side effects. Detailed evidence and the required change/validation matrix are in [the D-031 implementation review](D031_IMPLEMENTATION_REVIEW_2026-08-04.md).

## Parallel delivery dashboard

| Track | Committed outcome | Current state | Next bounded action | Gate / dependency |
|---|---|---|---|---|
| Shared contract | ACG critical kernel plus fixtures/fakes/conformance | corrected commit `857d5c06`; W1-S1 `CLOSED` | hold the contract stable while A packages consume it | consumed primitives are available to A packages |
| P1 Speech I/O | AIO + SR/SS Ports and real/fallback Adapters | P1A and the tested/reviewed P1B Browser fallback are committed | plan real Provider/device B/C work | Provider/device evidence required for B/C closure |
| P2 Realtime | CR + RM + II + AB with real non-blocking path | P2A and the tested/reviewed W1-X2 fake vertical are committed; no real transport/Agent route | define the real Agent compatibility path | real B/C waits for consumed consumer Gate |
| P3alpha Task | TC + ED + VB, D0 and progress return | P3A committed; P3 fake vertical tested; D-031 monitor/fail-closed behavior verified, but AutoHarness execution target is unbound | choose project-bound execution versus explicit runtime-extension Demo, then add preflight target/artifact agreement | no positive real run before the mixed-contract defect is removed; durability/auth and formal Store/Event remain later Gates |
| Integration | cumulative Demo, observability, fault injection, Windows path | three fake verticals composed; opt-in Browser P1 fallback wired; implementation is committed and reviewed | prepare the next real Provider/Agent/Harness routes without claiming a user-facing Demo | Week 2 90% Gate and Week 4 Alpha Gate |

Tracks are dependency-driven but not globally serialized. Multiple bounded packages may execute concurrently after their consumed contract subset is frozen. Sol retains final judgment for cross-module semantics, high-risk closure, the Week 2 Gate, and the Week 4 Gate.

## Current execution policy

- GPT/Sol is the only current lane for design, implementation, tests, and review; no package depends on DeepSeek.
- Do not remind, delegate, or switch work to DeepSeek or another external execution model.
- Historical external output is reference material only and must be revalidated before selective reuse.
- Keep implementation and review in the current GPT/Sol task, including work estimated above one hour.
- Tier 2/3 semantics and release decisions remain with GPT/Sol; Git commit and push approvals remain separate.
- D-053 applies prospectively: Tier 2/3 implementation batches use self-review, cold complete-diff review, and independent `/review` or a documented equivalent; Tier 1 normally uses the first two unless its boundary raises the risk.

## D-031 decision point

D-054 records the W1-S3 result as `TIMEBOX`. The user approved the 1–2 working-day package on 2026-08-04, and its minimal legacy Demo Adapter is committed in `d84fd388`:

- if formal `TC-B + TaskEvent/projection` can enter the cumulative Demo by Day 7, skip or reduce D-031;
- otherwise timebox a minimal single-task poll monitor to 1–2 working days;
- retain one in-flight read, exact identity/target, stale-result fencing, truthful unknown/error, no Chat mutation, and safe notification arbitration;
- do not expand the disposable polling path into general recovery, multi-task control, durable replay, or a second Task Core.

The detailed original pre-review remains available in the frozen Sol review record; it is an input, not a mandatory full implementation scope.

This remains a temporary legacy Adapter and earns no formal Task Core/Event replacement credit. Monitor and fail-closed evidence are complete, but D-031 remains `PARTIAL`: the project selected by the Web task is not the repository used by the fixed extension pipeline. Before more code, choose either a project-bound Executor/Harness Adapter (recommended for “后台代码优化任务”) or an explicitly renamed runtime-extension Demo. Regardless of choice, reject mismatched target/execution/artifact facts before model work and expose the effective execution root as backend provenance. Do not continue expanding TaskBridge or the monitor into execution authority.

## Demo Replacement Ledger

Completion is not derived from source lines, test counts, or module-name counts. The Week 2 acceptance document owns the scoring rules; this table carries only current route state.

| Weighted journey | Weight | Current route | Current credit | Target route / replacement condition |
|---|---:|---|---:|---|
| P1 capture, recognition, synthesis, playout | 20 | V0 Browser Speech/TTS fallback | 0 | formal AIO/SR/SS Ports with real Adapter evidence; fallback remains available |
| P2 lifecycle, non-blocking Agent work, barge-in/fence/history | 40 | local hook/epoch, Chat path, explicit interruption | 0 | CR/RM/II/AB own the route and pass stale/cancel/presentation evidence |
| P3alpha task create/control/events/progress | 25 | legacy schedule Bridge/task card plus D-031 single-page polling; no formal event projection | 0 | TC/ED/VB own real create/get/list/status/cancel/events, D0 and progress return |
| Context, failure/degradation, observability and flag-off | 15 | partial disclosure, runbooks and legacy logs | 0 | versioned facts, route labels, trace/evidence, truthful degradation and text regression |
| **Total** | **100** | integrated scoring has not started | **0** | Week 2 requires at least 90 and every mandatory invariant |

Credit changes only after the corresponding acceptance evidence exists. A substitute may demonstrate a category but does not automatically receive formal-module credit.

## Test and review policy

D-032 is risk-proportional under D-046:

- **Tier 0 — documentation/mechanical/refactor:** affected checks and regression only;
- **Tier 1 — ordinary feature/Adapter/UI:** positive journey, key negative/flag-off cases, affected integration and regression;
- **Tier 2 — state/concurrency/mutation boundary:** scoped pre/post Sol review and all applicable scenario dimensions, including forbidden side effects;
- **Tier 3 — shared protocol, authority, security, durability, release Gate:** full D-032 matrix, fault/recovery evidence, immutable candidate and required E2E/manual evidence.

Related packages may share one design checkpoint, implementation batch, post-review, and commit. A separate pre-review commit/push for every small package is not required. Every commit and push still requires the exact separate approval specified by root `AGENTS.md`.

D-053 adds three-pass review for Tier 2/3 batches. Each pass records findings and fixes, affected tests rerun after fixes, and material semantic changes trigger another final cold complete-diff review. An unavailable `/review` is recorded as a limitation with the actual substitute; it is never reported as executed.

## Known blockers and risks

- The three-to-four-week target assumed at least three useful parallel implementation lanes; D-052 now fixes execution to one GPT/Sol lane, so the 31-package, roughly 47–78 sequential-person-day estimate must be recalculated from actual progress.
- No real streaming Speech Provider, media transport, or Windows device baseline is selected/restored in Git.
- The repository `.venv` exists and is the verified project runtime. Pytest is also installed in the system-default Python, but that environment lacks other project dependencies; frontend dependencies, local `tsc`, focused Node tests, and the Vite production build run successfully in this worktree.
- Current runbook modes are mutually exclusive; Integrated mode is a documented target but not yet runnable.
- Browser Speech first-pass fidelity remains weak for critical Chinese/technical tokens.
- Current supplement/cancel behavior is not a production generation or tool-side-effect fence.
- Existing task scope is single-user request consistency, not authenticated authorization; existing JSON guarantees are same-process, not exactly-once.
- D-031 currently mixes two targets: Web authorization/result validation uses the selected project, while AutoHarness executes configured Agent Core through an extension-only pipeline. Another positive real run is blocked until this is rejected up front or replaced by a coherent executor/artifact contract.
- Large compatibility aggregators (`useLiveVoiceDemo`, the frontend TaskBridge, and schedule service/store) already contain more responsibility than their final Adapter roles; continued expansion would create competing authorities. Core frontend files also contain broad formatting churn that should be reduced mechanically before formal merge.
- Credentials, provider configuration, project registration, runtime data, browser permissions/devices, and network availability remain machine-private.

## Verification ledger

- V0 exact-SHA acceptance: Gate 0–6 PASS; see immutable evidence.
- Runtime-tested cleaned integration SHA: `ac988b85e8a21eb4f378086bab58dac6a4d55d82`.
- Historical Post-V0 backend: contract/Web handler `122/122`, schedule request/task service `104/104` PASS.
- Historical Post-V0 frontend: 12 focused Live Voice scripts, TypeScript, and Vite production build PASS.
- W1-K1 candidate `6ce74a4b`: Python focused suites `92 passed`; TypeScript fresh single-file compilation and `41` focused tests succeeded; adversarial probes still failed the accepted semantics, so W1-S1 was not accepted. Full Vite build was not counted because the detached review worktree could not resolve local frontend dependencies.
- Committed Sol W1-K1 candidate after three reviews: historical result `76` Python and `24` TypeScript tests plus Ruff/build/link checks passed; a later review reopened W1-S1 for the two P1 corrections recorded above.
- Corrected W1-K1 commit `857d5c06`: `77` Python v1+v2 tests and `25` TypeScript tests pass; Ruff, Prettier, Vite production build, links, diff check, and final diff review pass.
- W1-X1 commit `ac608738`: strict planned TypeScript compile and `17` focused tests pass; Prettier, Vite production build, diff check, and final diff review pass.
- Week 1 A-package commit containing this status: Python focused plus affected regressions `188 passed` (`53` focused A-package cases); frontend shared contract/conversation/audio `25 + 8 + 8 = 41 passed`; Ruff, Prettier, and Vite production build pass. The applicable checks were repeated after commit; see [the detailed review](W1_A_PACKAGE_REVIEW_2026-08-04.md).
- Committed W1-X2 implementation: backend `64 passed` with Ruff format/check; frontend fake/telemetry plus affected legacy suites `55 passed`; production build passed.
- Committed W1-P1B implementation: Adapter tests `9 passed`, planned legacy suites `82 passed`, standalone TypeScript/esbuild checks, default-off build, and flag-on build passed. All three D-053 reviews are complete; the independent finding is fixed and covered.
- D-031 commit `d84fd388`: monitor `22`, Bridge `47`, client `17`, and adapter `19` frontend tests pass; adjacent core `9`, turn lifecycle `16`, and TTS ownership `2` pass; schedule service plus WebSocket handlers `115 passed`; targeted Ruff passes; default-off and task-flag-on production builds pass. `d031-05` added real evidence for unconfirmed zero mutation, one run/task, same-task polling, terminal failure adoption/stop, and zero-effect rejection. It failed positive delivery because AutoHarness used configured Agent Core/runtime-extension storage instead of the selected project; ASR was not causal. The manually captured 2,665-row TSV omitted 140 non-ASCII paths and is not evidence.

## Next actions

1. Before changing D-031 again, choose the coherent product contract documented in its review: project-bound code execution (recommended) or an explicitly restricted runtime-extension Demo. Do not apply a one-field `repo_url` patch without this decision.
2. Add a bounded preflight that resolves one effective execution root/artifact kind and rejects target/pipeline/result mismatches before model, clone, extension, or target side effects; keep execution authority out of the monitor and legacy TaskBridge.
3. Implement the chosen Executor/Harness Adapter path and pass the automated plus fresh real-service matrix in the D-031 review, including semantic target output, zero forbidden effects, truthful success, terminal polling stop, and at-most-once speech.
4. Keep the resulting documentation changes uncommitted until that validation is complete, then report exact scope/diff/tests/exclusions and request commit or amend approval; request push approval separately.
5. After the real P2 Agent route passes code review, stop and remind the user before starting cumulative real-service validation; do not wait until the final Week 2 Gate for its first run.
