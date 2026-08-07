# Live Voice W2 Integrated Demo acceptance

> Run state, current score and implementation facts: [STATUS.md](../STATUS.md)
> Authority: D-046, D-055, D-060, D-061, D-062 and [POST_V0_DELIVERY_ROADMAP.md](../roadmap/POST_V0_DELIVERY_ROADMAP.md)
> Showcase: [INTEGRATED_SHOWCASE.md](../demo/INTEGRATED_SHOWCASE.md)

This contract decides whether the cumulative P1/P2/P3alpha Demo has reached 90%. It does not modify or rerun the frozen V0 release claim and does not sign the Week 3–4 Integrated Web Alpha.

`W2` names the cumulative delivery-order Gate. It is not a promised calendar week or Day 10 deadline under either D-052's default allocation or the D-060/D-062 bounded adaptive-execution exception; lane count and worker form may change by batch, while this Gate's behavior, scoring and evidence requirements remain unchanged.

## 1. Candidate and evidence rules

- Run on one immutable candidate containing every code, test, fixture, flag, route-label and documentation input used by the Demo.
- Record exact SHA, dirty state, runtime versions, Provider/Executor labels, browser/OS/device/network/origin-security labels, and sanitized route traces.
- Agent, Tool, task ID, status, outcome and result must come from real sources. Fakes are allowed only for automated conformance/fault injection and never as showcase success evidence.
- Every journey segment must identify its actual owner and route as `formal`, `fallback`, `demo_substitute`, `unsupported`, or `unknown`.
- Git cannot restore credentials, Provider configuration, project registration, runtime data, permissions, devices or network; their availability and exact test boundary must be recorded without secrets.

## 2. Mandatory invariants

Any failure below makes the Gate `FAIL` regardless of arithmetic score:

1. partial/interim/uncommitted speech causes zero Agent, Tool, Task, history or other mutation;
2. a committed conversational Turn and a committed task command each dispatch at most once under their declared idempotency contract;
3. stale response/generation/session/task/attempt/target output applies to UI, audio, history, Tool or Task state zero times;
4. playback stop, response cancel, round cancel and task cancel never widen into another scope;
5. wrong/missing/expired scope or target fails closed before protected read/control/mutation;
6. ACK, timeout, queued/enqueued, unknown, unsupported and unavailable never appear as terminal, presented or successful facts;
7. destructive or side-effecting task commands require the exact committed intent, target and confirmation required by policy;
8. feature/capability off leaves the original text Chat/E2A/Agent/Tool/TTS/Task path usable with zero hidden new timers, media, commands or persistence writes;
9. fallback/substitute state is visible and the Demo never claims Production, exactly-once, rollback, D1/D2 or complete P3 without evidence;
10. exit/unmount closes microphone and audible output and prevents late local effects.

## 3. Weighted Replacement Ledger

Score only evidence observed on the candidate. A full item requires its target module to own the route; a fallback may receive full credit only when it is an Adapter behind the formal Port and its capability/error provenance is visible.

### P1 Speech I/O — 20 points

| Item | Points | Full-credit evidence |
|---|---:|---|
| Audio capture/playout ownership | 5 | formal AIO route, device/permission lifecycle, stop and failure evidence |
| Recognition Port and Adapter | 6 | raw hypothesis/provenance, partial/final/cancel order, real Adapter/fallback, critical-token policy |
| Synthesis Port and Adapter | 5 | response/text-span provenance, real/fallback output, stale/cancel behavior, no display-text rewrite |
| Commit, clarification and text degradation | 4 | only eligible committed input dispatches; permission/Provider failure returns to usable text |

### P2 Realtime Conversation — 40 points

| Item | Points | Full-credit evidence |
|---|---:|---|
| Conversation Runtime identity/lifecycle/fence | 10 | canonical interaction/turn/response/generation and late-output zero effects |
| Realtime Media | 8 | concurrent ingress/playout, bounded queue/backpressure, control ACK and fault evidence |
| Interaction Engine | 8 | EOT/commit/barge-in/stop/revise actions with Engine not owning lifecycle truth |
| Agent Bridge | 8 | committed non-blocking dispatch, real Agent/Tool, source progress and no TaskCommand leakage |
| Presentation/history truth | 6 | produced/enqueued/presented/invalidated are distinct and interrupted prefix handling is truthful |

### P3alpha Task Control — 25 points

| Item | Points | Full-credit evidence |
|---|---:|---|
| Task Core identity, command ledger and TaskEvent truth | 8 | real create/get/list/status/cancel/events, reducer and terminal outcome |
| D0 Executor | 6 | real task survives voice/Session disconnect while app/Executor live; exact cancel/status and restart reconciliation |
| Voice–Task Bridge | 5 | committed text/voice mapping, target resolution, clarification/confirmation and zero partial command |
| Progress/result return | 4 | TaskEvent-derived WorkProgress returns through origin surface without direct TTS or Chat truth mutation |
| Task UI/control integration | 2 | exact structured controls and truthful task/event/provenance display |

A real legacy schedule/Bridge plus a timeboxed D-031 poll Adapter may receive at most **15/25** for P3alpha, and only when it passes the same mandatory identity, committed-only, truthful-state and no-wrong-task rules. It cannot claim TaskEvent/Core/Executor credit it does not implement.

### Cross-cutting — 15 points

| Item | Points | Full-credit evidence |
|---|---:|---|
| Route telemetry | 4 | every showcase segment proves formal/fallback/substitute owner and version |
| Context | 3 | stable project/resource identity, revision/scope/permission facts and no secret serialization |
| Failure/degradation | 3 | Provider/media/Agent/Executor faults produce truthful bounded fallback/error |
| Observability/fault injection | 3 | correlated trace, queue/cancel/fence/task events and reproducible injected failures |
| Feature-off/text regression | 2 | affected automated and real text route evidence |

## 4. Gate sequence

### Gate 0 — identity and environment

Candidate SHA, clean worktree, isolated runtime data, routes/flags, Provider/Executor/device labels and secrets boundary are recorded. Failure to identify the actual project or route is a `FAIL`.

### Gate 1 — automated evidence

Run all affected Tier 2/3 contract/conformance suites, relevant P1/P2/P3alpha integration tests, fault injection, text/flag-off regressions, TypeScript/build and applicable Python checks. No unexplained required gap or flaky pass is accepted.

### Gate 2 — cumulative real journey

On one Session and one cumulative mode:

1. speak a request that reaches the real Agent and Tool and hear the truthful response;
2. continue during Agent work and demonstrate the declared non-blocking/interruption route;
3. create one real D0 task through committed intent and exact confirmation;
4. continue normal conversation while the task runs;
5. query/cancel or observe the exact task and receive truthful progress/terminal facts through the origin surface;
6. demonstrate one Provider/media/permission or Executor degradation without losing text fallback;
7. inspect route telemetry proving which formal/fallback/substitute implementation owned every step.

### Gate 3 — scoring

The evidence owner updates the itemized calculation. Pass requires:

- total score `>= 90/100`;
- P1 `>= 16/20`, P2 `>= 36/40`, P3alpha `>= 20/25`, Cross-cutting `>= 12/15`;
- all mandatory invariants PASS;
- no score based solely on a design, fake, blank result field or planned package.

The P3alpha minimum means a legacy-only D-031 route capped at 15 cannot by itself pass Week 2; at least part of the formal TC/ED/VB path must already own the cumulative Demo.

### Gate 4 — repeatability and recovery

- Complete the integrated showcase three consecutive times on the same candidate and environment.
- Inject at least one retriable and one non-retriable failure in each active capability plane without stale effects or false success.
- Restart the application/runtime as applicable and report each in-flight P3alpha fact as active, terminal, interrupted, unknown or visibly reconciliation-pending according to evidence; do not claim continuation that did not occur.

## 5. Result record

```text
candidate_sha:
worktree_clean:
environment_labels:
P1_score: __ / 20
P2_score: __ / 40
P3alpha_score: __ / 25
cross_cutting_score: __ / 15
total_score: __ / 100
mandatory_invariants: PASS / FAIL
showcase_consecutive_runs: __ / 3
formal_routes:
fallback_routes:
demo_substitutes:
unsupported_or_unknown:
failed_or_missing_evidence:
gate_result: PASS / PARTIAL / FAIL
Sol_sign_off:
```

A PASS proves the W2 cumulative Demo Gate only. It does not prove a calendar deadline, and every formal module remains subject to its W3/W4 Alpha evidence.
