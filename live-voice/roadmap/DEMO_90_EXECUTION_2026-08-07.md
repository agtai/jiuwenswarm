# Live Voice W2 90% Demo execution packet

> Accepted 2026-08-07 under D-046 and D-062.
>
> This is the stable W2 task, dependency, ownership and exit contract. Current branch, progress, blockers, score and next active lane live only in [STATUS](../STATUS.md). Pass/fail remains exclusively owned by [Integrated Demo acceptance](../validation/INTEGRATED_DEMO_ACCEPTANCE.md).
>
> **Superseded acceptance procedure:** D-071 retires this packet's score, signature, immutable-evidence and repeated-showcase Gate. Keep its package boundaries and historical estimates only; current W2 closure is automated verification plus one complete human product acceptance under the acceptance contract and STATUS.

## 1. Outcome and anti-drift rule

This packet originally targeted one immutable, scored W2 evidence set. D-071 supersedes that exit: the current milestone is one cumulative Integrated Demo whose applicable automated checks pass and whose complete human product journey passes once. W2 is followed by Integrated Web Alpha; complete P3 and production hardening follow Alpha.

A task belongs on the W2 critical path only when it does at least one of the following:

- enables a scored real P1, P2, P3alpha or cross-cutting segment;
- closes a mandatory invariant or a failure/recovery requirement;
- supplies a machine-private dependency or environment fact needed by the cumulative route;
- composes already reviewed leaves into the single product route;
- produces required automated, real-path or immutable candidate evidence.

Work unique to W3/W4 or Later does not consume W2 critical-path capacity unless it is an actual dependency of the selected W2 route. If all eligible W2 work is externally blocked, Main may release idle capacity to a bounded later task that preserves the same architecture and does not create a second authority.

## 2. Work packages

Effort bands are engineering activity estimates assuming current foundations remain usable and required private dependencies are available. They are not calendar commitments and are not added mechanically under parallel execution.

| ID | Name | Stable content and exit | Nature | Effort | Main dependencies |
|---|---|---|---|---:|---|
| `D90-00` | Candidate and environment baseline | Declare isolated runtime data, exact project/model/Provider/Executor/browser/device/network/origin labels, credentials boundary and evidence sinks | decision, configuration, preflight | `0.5–1d` | user/machine-private inputs |
| `D90-P1` | Real Speech/Media vertical | Registered AIO/SR/SS/Media route, selected real/fallback Adapter, committed-only capture, playout/stop, permission/Provider degradation and zero-persistence evidence | Adapter code, integration, physical-device debugging | `4–6d` | `D90-00`, Provider/transport capability |
| `D90-P2` | Cumulative realtime conversation | Extend the proven real Agent/Tool text seam through the selected Speech/Media route; cover multi-turn, non-blocking work, barge-in/cancel, generation fence, presentation/history and required reconnect/fault behavior | runtime code, integration, concurrency debugging | `2–4d` | final route consumes `D90-P1`; fake/text work can start earlier |
| `D90-P3F` | Disposable P3 fixture | Register a disposable Git Code project, persistent Session, model and runnable Executor; bind project/Code Agent/Git roots and govern runtime support paths | configuration, environment, real smoke | `0.5–1.5d` | `D90-00`, user-approved disposable target |
| `D90-P3` | Formal P3alpha vertical | Formal Core/Event/Executor/Voice-Task path for create/get/list/status/cancel/events, confirmation, D0 disconnect survival, exact progress/result and truthful restart reconciliation | backend/UI code, integration, Executor debugging | `4–6d` | `D90-P3F`, Main composition hooks |
| `D90-X` | Minimum evidence and degradation plane | Correlated route ownership, Context facts, active-plane retriable/non-retriable faults, feature-off/text regression and sanitized evidence capture | instrumentation, fault injection, tests | `1.5–3d` | event vocabulary; final correlation consumes integrated routes |
| `D90-COMP` | Cumulative product composition | One mode and one Session register eligible P1/P2/P3alpha/X routes through trusted Authority, exact cleanup and visible formal/fallback/substitute truth | Main-owned shared integration and UI | `2–4d` | reviewed usable P1/P2/P3 leaves and X instrumentation hooks |
| `D90-VERIFY` | Cumulative verification and review | Risk-proportional affected suites, build, negative/fault/flag-off regressions, coherent-batch cold review and required independent review | tests, review, fixes | `2–3d` | integrated candidate |
| `D90-ACCEPT` | W2 product acceptance | Identify the tested clean source; run applicable automated verification and one complete human cumulative journey; record actual limitations | browser/service E2E, human acceptance | `0.5–1d` | all prior exits |

## 3. Adaptive worker graph

Main derives the worker graph again at the start of every coherent batch. A logical lane exists only when its output can be reviewed and integrated independently. Lane count is neither a target nor a limit.

Selection rules:

1. Prefer independent critical-path leaves with disjoint files and semantic authority.
2. Merge tasks that must change the same authority, protocol, lifecycle or shared entrypoint.
3. Do not start a worker whose named dependency is unavailable and whose fake/leaf work is already complete.
4. Release capacity immediately when a lane becomes externally blocked; retain a precise fail-closed handoff rather than polling without progress.
5. Count Main and independent reviewers against actual tool concurrency. Never create work merely to occupy a slot.
6. Recompute the graph after every reviewed return, dependency release, semantic conflict or candidate failure.

Worker forms:

- Use a separate Session/worktree for independent code that benefits from its own branch and commit.
- Use a bounded subagent for read-only discovery, focused tests, cold review, or explicitly non-overlapping shared-worktree edits.
- A shared-worktree subagent never changes branch, index or history; Main owns its Git operations.
- Main retains shared Authority/contracts, central product Composition, Gateway/AgentServer dispatch, integrated Web entrypoints, cumulative evidence and final Gates.

The historical P1/P2/P3alpha/X split remains a useful candidate graph, not a fixed allocation. With four total execution slots a typical batch may use Main plus three workers and time-slice the fourth logical family; another batch may use fewer or more logical lanes as dependencies permit.

## 4. Ownership and integration

The reusable file boundaries and Main-only list in the [Alpha parallel plan](ALPHA_PARALLEL_EXECUTION_2026-08-06.md) remain the default. The task packet for each active lane must narrow them further to exact files, positive behavior, negative/fault/flag-off scenarios, forbidden effects, tests and exclusions.

Only Main performs integration, staging, commit or branch-history changes in the integration worktree. A shared-worktree subagent may be its sole active filesystem editor under an explicit lease naming the exact files; Main and other agents do not edit that worktree until the lease returns. A separate-worktree worker returns base SHA, branch, final reviewed commit, exact files, commands/results, review closure, unavailable hooks and risks, and never integrates its own return. Shared-worktree subagent changes remain uncommitted until Main completes the whole-diff review.

D-061 applies: focused checks and review close inside each coherent lane; Main runs one cumulative smoke after the complete reviewed integration batch. Semantic conflict resolution or integration glue receives affected checks before that smoke. Remote refs remain outside the local exception and always require exact user approval.

## 5. Execution waves

1. **Environment release:** close `D90-00` and start `D90-P3F`; identify every external blocker without exposing secrets.
2. **Independent vertical work:** derive concurrent `D90-P1`, `D90-P2`, `D90-P3` and `D90-X` leaves whose dependencies exist; X may prepare instrumentation before the cumulative route exists.
3. **Single-writer composition:** Main completes `D90-COMP` in real dependency order and keeps unavailable routes fail-closed; X then closes correlation against the actual composed lifecycle.
4. **Verification closure:** run `D90-VERIFY`, fix findings in the owning lane and rerun affected checks.
5. **Product acceptance:** run `D90-ACCEPT` once under D-071; no signature, fixed artifact set, numeric score or repeated full showcase is required.

## 6. W2 exclusions and later handoff

W2 does not require work solely for complete-P3 update/provide-input/pause/resume/reprioritize, D1/D2, production multitenant authorization, a public browser/platform matrix, RC operations or generalized rollback. A controlled localhost candidate is permitted by the W2 acceptance contract; non-localhost evidence must satisfy its declared HTTPS/WSS/proxy boundary. A production X-OBS backend, long-term SLO/retention and public deployment remain Alpha/Later work unless the chosen W2 route actually consumes them.

After W2 PASS, STATUS selects a new Integrated Web Alpha execution packet or explicitly reactivates the applicable Alpha work from the earlier plan. After Alpha PASS, STATUS moves to complete P3 and production scope. No worker advances the milestone from code, test count or appearance alone.
