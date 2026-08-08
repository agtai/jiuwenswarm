# W2 90% Integrated Demo source-candidate review

> Review date: 2026-08-08  
> Implementation commit: `2fdf849a` (`feat(live-voice): complete W2 integrated demo source route`)  
> Runtime acceptance authority: [Integrated Demo acceptance](validation/INTEGRATED_DEMO_ACCEPTANCE.md)  
> Mutable state: [STATUS.md](STATUS.md)

This is the frozen implementation and automated-verification record for the W2 cumulative source candidate. It does not award Replacement Ledger points. Real Provider, device, Agent/Tool, durable restart, fault, assisted-witness and signed-artifact evidence must still be collected against one clean immutable candidate before the Gate may return PASS.

## Reviewed scope

- P1: stock-Web microphone capture and rendered playout, dedicated Gateway uplink/downlink registration, bounded batch Speech RPC, and fail-closed provider/result validation.
- P2: exact committed Agent/Tool dispatch, formal round/history/presentation ownership, one-use binary downlink authority, render-driven ACK, next-turn uplink overlap, and exact barge-in/cancel fencing.
- P3alpha: authenticated query/progress/create/cancel composition, direct D0 project Executor, durable TaskEvent/Attempt authority, startup reconciliation, and voice-origin handoff.
- X-OBS/Gate: exact product-source records, separate closed Gateway/AgentServer JSONL v2 artifacts, producer-bound signatures, external root-authorized artifact subjects, cross-artifact causal/task derivation, fault/restart/showcase evaluation, and strict CLI import.
- Product composition and lifecycle: default-off activation, startup/shutdown ordering, retained cleanup owners, privacy boundary, runbook, and acceptance contract.

## D-053 review closure

### Implementation self-review

The implementation review found and corrected:

- Speech RPC result transforms could return a non-object; the route now fails closed as `CAPABILITY_UNAVAILABLE / MEDIA_DOWNLINK_UNAVAILABLE`, with positive and negative coverage.
- Physical WebSocket close could race the downlink completion fact; registry completion now occurs before leaf close through an explicit completion callback.
- A client-declared overlap could overstate P2 realtime media; credit now requires the exact active uplink ticket and at least one accepted real frame during bounded downlink playout.
- Shutdown could close evidence before final P3 reconciliation; Product composition stops first, final P3 reconciliation runs second, and the evidence owner closes last. Failed cleanup owners remain retained for exact retry.
- Product W2 failure facts could use an inconsistent source; operation-derived source identity is now preserved and tested.

### Cold complete-diff review

The cold review re-read the complete W2 diff against the execution packet, repository rules, existing behavior, and actual tests. It corrected the following Gate semantics:

- Cross-producer order is derived from `observed_at`; per-artifact slot sequence is append order only and cannot claim cross-producer causality.
- All seven positive-journey steps must share one exact runtime artifact set, ordered correlation chain, and exact task chain.
- Root-authorized artifact slots require nonempty exact subjects, and import equality is unconditional.
- `P3_EXECUTOR` must intersect the exact Core/restart/D0 task.
- Speech synthesis and response presentation are unordered siblings after the Agent final; the step ends at their later completion.
- Actual Task producer order is origin, create, then bridge.

A final regression constructs a normal Gateway to AgentServer to Gateway to AgentServer journey with exact time, correlation and task bindings and passes the evaluator.

### Independent review

Literal `/review` was not available in this execution surface. A separate read-only independent reviewer was used as the recorded equivalent; it did not edit files or run tests.

The initial independent pass returned FAIL with three P1 findings and one P2 finding: cross-producer slot ordering was treated as causal, the seven-step journey was not bound to one exact artifact set, root-authorized subjects were underconstrained, and the exact D0 task was not intersected. After fixes, the follow-up found one remaining P1 issue in the presentation/synthesis sibling ordering. That issue was fixed and regression-tested. The final independent pass returned PASS with no actionable P0-P2 findings.

## Automated verification

All commands ran from the repository root on Windows against the code that became implementation commit `2fdf849a`.

| Check | Result |
|---|---|
| Affected backend cumulative matrix | `656 passed, 2 skipped` |
| Gate/CLI/product-observability focused matrix | `69 passed` |
| Frontend integrated Web tests | `137/137 passed` |
| Frontend Gateway batch-Speech tests | `23/23 passed` |
| Frontend production build | PASS, 4512 modules; only existing locale/caniuse/chunk-size warnings |
| Ruff over 43 changed Python files, excluding two legacy entry files | PASS |
| Complete backend unit suite, final exact source tree | `5383 passed, 9 skipped, 13 failed` in 317.89 seconds |
| `git diff --check` before implementation freeze | PASS |

The 13 complete-suite failures are pre-existing platform/baseline exclusions outside this W2 diff:

- two shell-process-registry cases requiring POSIX process tools;
- one deterministic existing `AgentManager` same-key cleanup/construction concurrency failure;
- one team-entity symlink test requiring Windows symlink privilege;
- three CLI tests asserting POSIX path spelling on Windows;
- three AgentOS router tests asserting POSIX path spelling on Windows;
- two HookExecutor tests requiring `sh`/POSIX shell behavior;
- one dependency-constraint test reading UTF-8 `pyproject.toml` through the Windows cp1252 default.

The two changed legacy entry files retain four Ruff findings outside the changed hunks: `app_web.py` has existing F401/F541 and `app_gateway.py` has existing F841/F821. They were not modified merely to conceal unrelated baseline debt.

One affected run executed concurrently with the full suite produced a timeout-sensitive failure in `test_composition_close_raises_until_retained_worker_is_terminal`. It passed immediately in isolation and in ten consecutive fresh isolated processes. The final affected cumulative run passed; the overlapping run is retained as a resource-contention limitation rather than being represented as an unexplained flaky pass.

## Disposable P3 target prepared

A repository outside the product worktree was created at `C:\Users\admin\Desktop\jiuwenswarm-live-voice-w2-fixture-20260808`. It is a clean local Git repository on `master`, has no remote, has fixture commit `5ad6692d2f2e7bad939a350bf7ebad1268e0e97c`, and its two tests pass. Runtime support directories are governed by its `.gitignore`.

The fixture is not yet a runnable Gate target: it still needs JiuwenSwarm project registration, an available model, one saved persistent Session, isolated runtime data, and private bounded P3 authority configuration.

## Remaining external Gate boundary

Automated/source closure is complete, but the formal score remains `0/100` until all positive evidence is real and all mandatory invariants pass. The remaining work requires:

1. Private Speech Provider API base/key/provider/model/voice configuration on the server machine.
2. One isolated `JIUWENSWARM_DATA_DIR`, saved Session, registered disposable project/model, and bounded bearer/principal/project/expiry authority.
3. Chrome microphone/output permission, a real microphone/headphones path, and a human heard/seen witness.
4. An externally controlled root-signed trust policy with predeclared runtime, assisted and review artifact subjects; signer private keys remain outside Git and evidence.
5. One controlled cumulative journey, retriable and non-retriable zero-effect faults, durable restart reconciliation, three consecutive showcases, artifact sealing/signing, and strict CLI evaluation.

The candidate therefore remains `SOURCE-INTEGRATED / GATE-PARTIAL / EVIDENCE OPEN`. A healthy prepared environment should need about 2-5 assisted hours for collection and Gate closure; initial Provider/project/device setup usually adds 20-45 minutes, or 1-3 hours if environment debugging is required.
