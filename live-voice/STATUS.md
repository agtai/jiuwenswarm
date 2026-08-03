# Live Voice current status

> Updated: 2026-08-03
> This is the only mutable source for current branch facts, milestones, track state, blockers, and next actions. Detailed design reviews and immutable evidence are linked rather than copied here.

## Git and release identity

- Development branch: `hx/0803_live_voice`.
- Upstream: `origin/hx/0803_live_voice`.
- Runtime implementation baseline reviewed by this consolidated planning record: `ac988b85e8a21eb4f378086bab58dac6a4d55d82`. Subsequent commits through the consolidated planning commit change documentation only. The planning commit intentionally does not self-record its SHA—verify actual HEAD and upstream at every resume.
- V0 immutable Released / Frozen baseline: `ee2896a4afb186e693c720476b6de10797e66f72` with Gate 0–6 PASS.
- Post-V0 foundation is integrated but remains partial; it is not formal P1/P2/P3alpha closure.
- D-041's Sol/non-Sol responsibility split remains active, while its former D-031-first ordering and universal D-032 workflow are superseded by D-046/D-047. The superseded reasoning remains in the decisions and frozen pre-review record rather than a separate Git checkpoint.
- The previous Sol design batch is preserved in [SOL_MODULE_PRE_REVIEWS_2026-08-03.md](SOL_MODULE_PRE_REVIEWS_2026-08-03.md). Its blank non-Sol result fields are not current progress claims.
- D-048 freezes the next five working days in [WEEK_1_EXECUTION_PACKAGES_2026-08-03.md](roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md). The plan defines package contracts but carries no implementation progress; all code packages remain not started.

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
- accepted architecture designs for ACG-1, CR-A, SR-A/SS-A, and TC-A.

It does not yet contain:

- shared v2 contract types/fixtures/conformance runner;
- formal Conversation Runtime, response/generation fence, presented ledger, or real Realtime Media;
- P1 Speech Ports with a selected real streaming Provider and Windows Audio I/O closure;
- formal Task Core/Event Store/Executor Port, `events` API, restart reconciliation, or production AuthorizationContext;
- a runnable cumulative Integrated Demo mode or Week 2/Week 4 acceptance evidence.

D-047 records the accepted code-scope audit: the current V0 and task foundations retain their necessary safety regressions but are frozen as fallback, Demo substitute, or Compatibility Adapter. Do not add formal authority or platform features to `useLiveVoiceDemo`, the frontend TaskBridge, or the legacy `schedule.*`/JSON path; CR/TC/ED and the other target modules must take ownership through incremental Integrated-route replacement rather than a separate cleanup rewrite.

## Parallel delivery dashboard

| Track | Committed outcome | Current state | Next bounded action | Gate / dependency |
|---|---|---|---|---|
| Shared contract | ACG critical kernel plus fixtures/fakes/conformance | Sol plan complete; code not started | after the documentation commit, non-Sol executes `W1-K1`; Sol performs `W1-S1` | `W1-S1 CLOSED` unlocks consumed primitives |
| P1 Speech I/O | AIO + SR/SS Ports and real/fallback Adapters | V0 fallback exists; formal Ports not started | execute `W1-P1A`, then conditional Browser route `W1-P1B` | W1-S1 first; Provider/device evidence required for B/C closure |
| P2 Realtime | CR + RM + II + AB with real non-blocking path | design accepted; implementation not started | execute `W1-P2A-CR` and `W1-P2A-PORTS` against shared fakes | W1-S1 first; real B/C waits for consumed consumer Gate |
| P3alpha Task | TC + ED + VB, D0 and progress return | legacy foundation exists; formal Core not started | execute `W1-P3A-TC` and `W1-P3A-PORTS`; use actual progress at `W1-S3` | W1-S1 first; D-031 remains Day 5 conditional |
| Integration | cumulative Demo, observability, fault injection, Windows path | V0 only; modes are currently separate | execute `W1-X1`, then compose landed A packages in `W1-X2` | Week 2 90% Gate and Week 4 Alpha Gate |

Tracks are dependency-driven but not globally serialized. Multiple bounded packages may execute concurrently after their consumed contract subset is frozen. Sol retains final judgment for cross-module semantics, high-risk closure, the Week 2 Gate, and the Week 4 Gate.

## D-031 decision point

D-031 is no longer the unconditional first project task. It is a legacy Demo Adapter candidate for the P3alpha track:

- if formal `TC-B + TaskEvent/projection` can enter the cumulative Demo by Day 7, skip or reduce D-031;
- otherwise timebox a minimal single-task poll monitor to 1–2 working days;
- retain one in-flight read, exact identity/target, stale-result fencing, truthful unknown/error, no Chat mutation, and safe notification arbitration;
- do not expand the disposable polling path into general recovery, multi-task control, durable replay, or a second Task Core.

The detailed original pre-review remains available in the frozen Sol review record; it is an input, not a mandatory full implementation scope.

## Demo Replacement Ledger

Completion is not derived from source lines, test counts, or module-name counts. The Week 2 acceptance document owns the scoring rules; this table carries only current route state.

| Weighted journey | Weight | Current route | Current credit | Target route / replacement condition |
|---|---:|---|---:|---|
| P1 capture, recognition, synthesis, playout | 20 | V0 Browser Speech/TTS fallback | 0 | formal AIO/SR/SS Ports with real Adapter evidence; fallback remains available |
| P2 lifecycle, non-blocking Agent work, barge-in/fence/history | 40 | local hook/epoch, Chat path, explicit interruption | 0 | CR/RM/II/AB own the route and pass stale/cancel/presentation evidence |
| P3alpha task create/control/events/progress | 25 | legacy schedule Bridge/task card; no continuous monitor | 0 | TC/ED/VB own real create/get/list/status/cancel/events, D0 and progress return |
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

## Known blockers and risks

- The three-to-four-week target assumes at least three useful parallel implementation lanes plus continuous integration; the complete solution lists 31 packages totaling roughly 47–78 sequential person-days before full-P3 extensions.
- No real streaming Speech Provider, media transport, or Windows device baseline is selected/restored in Git.
- This workspace currently has neither a repository `.venv` nor frontend `node_modules`; Week 1 verification commands cannot be counted as run until dependencies are restored.
- Current runbook modes are mutually exclusive; Integrated mode is a documented target but not yet runnable.
- Browser Speech first-pass fidelity remains weak for critical Chinese/technical tokens.
- Current supplement/cancel behavior is not a production generation or tool-side-effect fence.
- Existing task scope is single-user request consistency, not authenticated authorization; existing JSON guarantees are same-process, not exactly-once.
- Large compatibility aggregators (`useLiveVoiceDemo`, the frontend TaskBridge, and schedule service/store) already contain more responsibility than their final Adapter roles; continued expansion would create competing authorities. Core frontend files also contain broad formatting churn that should be reduced mechanically before formal merge.
- Credentials, provider configuration, project registration, runtime data, browser permissions/devices, and network availability remain machine-private.

## Verification ledger

- V0 exact-SHA acceptance: Gate 0–6 PASS; see immutable evidence.
- Runtime-tested cleaned integration SHA: `ac988b85e8a21eb4f378086bab58dac6a4d55d82`.
- Historical Post-V0 backend: contract/Web handler `122/122`, schedule request/task service `104/104` PASS.
- Historical Post-V0 frontend: 12 focused Live Voice scripts, TypeScript, and Vite production build PASS.
- These are historical results, not reruns for the current uncommitted documentation update and not Week 2/Week 4 evidence.

## Next actions

1. If the D-048 documentation candidate is still uncommitted, review its exact scope/message and obtain the required approval; once that commit exists, do not repeat this step. Push still requires separate approval.
2. After that documentation commit, switch to the non-Sol executor and start `W1-K1`; a separate lane may start pure `W1-X1`. Keep implementation uncommitted and return the exact diff/evidence to Sol.
3. Sol performs `W1-S1`; only a `CLOSED` consumed kernel unlocks `W1-P1A`, `W1-P2A-*`, and `W1-P3A-*`. Landed A packages enter `W1-X2` continuously and remain truthfully labeled.
4. Sol performs grouped `W1-S2`, then at `W1-S3`/Day 5 decides D-031 `SKIP/REDUCE/TIMEBOX` from actual TC/Event progress.
5. Run [INTEGRATED_DEMO_ACCEPTANCE.md](validation/INTEGRATED_DEMO_ACCEPTANCE.md) at Week 2 and [ALPHA_ACCEPTANCE.md](validation/ALPHA_ACCEPTANCE.md) at Week 3–4.
