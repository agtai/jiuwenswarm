# Live Voice Alpha Wave A+B execution packet

> Frozen: 2026-08-07
>
> Baseline: pushed `hx/0803_live_voice` commit `7876e1ae9caad28535abcc674d6b02f72553fe4f`
>
> Integration branch: local `codex/lv-alpha-ab-integration`, no upstream
>
> Authority: D-046, D-053, D-060, D-061 and the accepted [Alpha parallel execution plan](ALPHA_PARALLEL_EXECUTION_2026-08-06.md)
>
> Role: stable task, ownership, review and recovery contract. Mutable progress, candidate HEAD and blockers remain exclusively in [STATUS](../STATUS.md).

## 1. Outcome and truth boundary

This batch runs Wave A and every Wave B slice permitted by real repository and machine dependencies without pausing between waves. It ends at one clean, reviewed, locally integrated and unpushed candidate. It does not modify the `hx/0803_live_voice` ref, update any remote ref, run Wave C physical acceptance, change the Replacement Ledger from `0/100`, or claim Integrated Demo, Web Alpha or production readiness.

Contracts, mocks, fakes, package tests, registration and hardening remain distinct from an observed real product path. A missing Provider, credential, browser/device condition, secure deployment, Executor registration, network service or X-OBS backend remains an exact fail-closed `unavailable` dependency; no Session may create a product fake to obtain a pass.

## 2. Seven logical Sessions and rolling schedule

| Logical Session | Persistent ownership | Write policy |
|---|---|---|
| Main Integration/Review | shared Authority/Composition contracts, Composition root/registry, AgentServer/Gateway/shared dispatch, stock-Web top-level panel/ChatPanel/package/i18n, integration glue/history, cumulative smoke and final docs/evidence | sole writer of the integration worktree |
| T1 P1 Speech/Media | browser Audio I/O and media transport leaves, server realtime-media leaves, selected real Speech Provider leaves only when a real hook exists | own task branch/worktree only |
| T2 P2 Runtime/Interaction | CR/II/AB runtime leaves, Harness/Agent adapter leaves, formal history/presentation leaves and their focused tests | own task branch/worktree only |
| T3 P3alpha Task | Task Core/Store/Executor, confirmation/voice-policy/progress leaves and new leaf controls/tests | own task branch/worktree only |
| T4 X-OBS/X-WEB/X-E2E | observability/exporter, Web diagnostic shell and leaf fault/E2E harnesses | own task branch/worktree only |
| Independent Reviewer | read-only review of task candidates, Main shared batches and final combined candidate | never modifies a candidate or creates a candidate commit |
| Environment/E2E Preflight | read-only audit of Provider, browser/media, proxy/deployment, Executor/project, exporter/backend and Wave C conditions | never reads or reports secrets and never changes product authority |

Concurrency slots may use a rolling schedule, but the seven roles, branch/worktree isolation and file ownership remain separate. All four implementation branches start at the governance commit produced from this packet. Only Main may grant a single-writer integration lease.

## 3. Wave A ownership and exit

- T1 adds the real Media activation/registration leaf on existing `realtime_media.py` and `browserGatewayMediaTransport.ts`, with Authority-first exact scope/correlation/generation/track binding, feature-off zero allocation/registration, a registered route-to-disk zero-persistence evidence hook and truthful Provider-unavailable behavior. It does not rewrite the LVM1 wire contract.
- T2 adds the product TurnCommit and exact PresentationAck/history leaf owners: committed input follows reserve -> CR accept -> commit/abort into the existing D-059 real Agent/Harness route, while only the acknowledged contiguous presented prefix enters formal history. Exact round cancel, generation fencing and retained shutdown remain intact.
- T3 reuses `p3_confirmation.py` to add a trusted confirmation issuer and bounded formal create/cancel mutation/reconciliation leaf. Exact principal/scope/operation/intent/target/expiry are mandatory; unknown mutation fails closed and reconciles. Existing authenticated query/text progress/delivery ACK remains intact.
- T4 makes nonformal route truth compatible with the retained X-OBS worker/Composition lifecycle, reuses the existing bounded exporter buffer/product Adapter, and supplies a leaf fault harness. Main alone registers X-OBS after Composition invariants pass; absent exporter/backend remains unavailable.

Wave A exit requires focused positive, negative, feature-off and affected regression tests; implementation self-review; concurrent Main cold complete-diff review and independent review; findings fixed by the owning Task; affected tests rerun; and a repeated final cold review after any semantic fix. Only after Main and Independent Reviewer both pass may a Task create its single final local commit and handoff manifest.

Main integrates reviewed commits in dependency order and runs only affected dependency checks after Wave A. It then releases Wave B immediately from the integrated Wave A HEAD without waiting for user input and without running the cumulative smoke early.

## 4. Wave B dependency release

- T1 connects selected batch/streaming STT/TTS, Browser AIO capture/playout, realtime Media, permission/device/page lifecycle, exact-response stop and text degradation only when the real Provider/config/transport hooks exist. Otherwise the exact segment remains unavailable.
- T2 connects realtime Media/voice to the text vertical, then the existing Interaction/VAD/EOT/working-notice, barge-in/stop/revise/delegate, audio PresentationAck and stale/cancel/loss/reconnect behaviors. Background work must not freeze foreground interaction.
- T3 connects formal voice only after the real CR handoff exists: TaskEvent -> WorkProgress -> origin surface, voice through CR and text through Web/UI, with atomic authority handoff, restart reconciliation and duplicate/gap/reorder/concurrent-task coverage. Missing Provider/CR handoff keeps formal voice unavailable.
- T4 connects a real exporter sink only if one exists, and advances secure-deployment diagnostics, fault injection, route/latency/queue/cancel/fence/task metrics and cumulative leaf E2E harnesses. It does not run Wave C physical acceptance or claim an Alpha Gate.

Each Wave B batch repeats the same oracle, review, single-final-commit and handoff rules. A real dependency may release only the dependent slice; absent external conditions do not block independent owned work.

## 5. Required pre-implementation state-machine oracle

Before editing, each implementation Session returns a concise oracle containing:

1. exact owned files and adjacent Main-only hooks requested;
2. positive business journey and the authority that owns each accepted effect;
3. owner identity, scope, correlation, generation, track/round/task/attempt and confirmation binding;
4. state transitions, terminal truth and ACK-versus-completion behavior;
5. feature-off forbidden allocations, registrations, calls, writes and external effects;
6. denied/unavailable behavior and zero downstream effects;
7. correlation/generation/binding mismatch behavior;
8. replay/idempotency/conflict behavior;
9. caller cancellation/timeout and retained cleanup ownership;
10. retry, tombstone and eviction bounds;
11. fallback/Demo/legacy non-regression;
12. focused, negative, flag-off and affected tests;
13. unavailable real dependencies and exact missing hooks;
14. explicit non-goals and file exclusions.

Main must confirm the oracle and freeze every adjacent shared interface before that Task may edit. A hook request does not authorize a Task to edit a Main-only file.

## 6. Standard handoff manifest and integration lease

Every final Task handoff contains:

```text
base_sha:
source_branch:
final_commit:
exact_files:
risk_tier:
test_commands_and_results:
self_review:
main_cold_review:
independent_review:
unavailable_hooks:
known_limits:
forbidden_effect_assertions:
```

Before each integration, Main records the source branch, exact reviewed commit, target `codex/lv-alpha-ab-integration` and cherry-pick/merge method. Mechanical conflicts stay within the lease; shared authority, lifecycle, route-truth, cleanup, correlation, generation or binding conflicts return to Main and the owner. Any Main integration glue is identified separately, receives affected tests and completes D-053 review when Tier 2/3 semantics change.

## 7. Review concurrency

Once a Task candidate is stable and self-reviewed, Main cold review and the read-only Independent Reviewer start concurrently. Findings return immediately to the owner while other candidates continue review. A Task commit exists only after both reviewers pass. Main shared/integration changes complete the same D-053 three passes; if literal `/review` is unavailable, the record names the independent read-only substitute and its limitations.

## 8. Cumulative smoke policy

### Green path

Task branches run focused and affected checks only. After all reviewed Wave A+B Task commits and Main integration glue have landed, Main runs one cumulative smoke at the exact final HEAD. It covers normal product routes; authority denied/unavailable; correlation/binding/generation mismatch; cleanup/retry/cancellation; feature-off zero side effects; fallback/Demo/legacy regressions; every new batch test; and the frontend production build.

### Failure path

If the final cumulative smoke fails, Main preserves the failing integration HEAD, complete logs and environment facts; classifies deterministic code versus flaky/environment failure; and never uses a destructive reset. Main creates a temporary diagnostic branch/worktree from the batch base, replays commits in original dependency order and runs the cumulative smoke after every commit until the first failing prefix is found. The finding returns to the owning Task, or to Main for a cross-module interaction. After the reviewed fix, affected tests run again; from the fix point every later commit is replayed and smoke-tested; then the complete final HEAD receives one last cumulative run. A combination-only failure is recorded as integration glue/interaction. Tests, assertions and fail-closed behavior are never weakened to obtain PASS.

## 9. Environment preflight return contract

The read-only Environment/E2E Session reports early:

- real Speech Provider configuration entrypoints and batch/streaming capabilities;
- only the presence/absence of legitimate machine-private credential configuration, never secret values;
- Browser<->Gateway transport/codec and Chrome secure-origin, permission, device and page-lifecycle facts;
- Gateway/AgentServer proxy, CSP, CORS, HTTPS/WSS topology;
- real Executor/project registration conditions;
- whether a real X-OBS exporter/backend exists;
- Wave B work possible without user intervention, exact unavailable hooks, and Wave C-only physical conditions;
- Wave C commands, fault matrix and evidence requirements without running the final acceptance.

## 10. Final closure

Closure requires reviewed Wave A and every real-dependency-permitted Wave B slice; one reviewed final commit per Task; dependency-ordered integration; reviewed integration glue; cumulative smoke and frontend build PASS; final Main cold review and independent combined review PASS; documentation link/duplicate/truth checks; a clean integration worktree; the `hx/0803_live_voice` ref unchanged; no remote update; Replacement Ledger still `0/100`; and no false Alpha/production-ready claim.

The final report records exact base/source/final/integration commits, actual real versus unavailable routes, tests and review fixes, Git status and commit range, recommended local integration method, and the Provider/Chrome/device/Executor/deployment conditions reserved for Wave C. Work then stops for the user's local-integration decision.
