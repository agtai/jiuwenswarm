# S8.5 incubation implementation review — 2026-08-13

> Milestone: post-Alpha S8.5 Competitive Showcase incubation
> Review updated: 2026-08-14
> Stage/node: S8 / A3 remains ready and not started
> Risk: Tier 3 shared Task/Store/Executor authority
> Comparison base: `a53856de0af12e2c1b11e6cc8f2dc0a18150a99a`
> Reviewed product source: `8be8398af63fe0ca8e7a853a5f804a41d04de9ca`
> Reviewed decision/showcase source: `fc7348f2`
> Disposition: the isolated product write path is implemented and affected
> checks pass; Tier 3 closure remains `PARTIAL`.

This record reviews the first isolated implementation of
[D-079](decisions/DECISIONS.md) and the
[S8.5 execution plan](roadmap/S8_5_COMPETITIVE_SHOWCASE_EXECUTION_PLAN_2026-08-13.md).
It does not close or modify S8/A3, authorize migration to the S8 branch, or
claim the complete S8.5 product journey.

## 1. Reviewed commits and scope

| Commit | Coherent scope | Review result |
|---|---|---|
| `bc53e75d` | D-079, bounded contract, plan, acceptance, showcase and competitor claim matrix | Main cold review passed |
| `caed0ff2` | immutable revision model and Task-Core-owned SQLite sidecar | Main cold review passed |
| `f13cfe8d` | committed-voice bridge, exact policy and confirmation binding | Main cold review passed |
| `0c994b1b` | predecessor fence, trusted clean successor, verifier and immutable execution ACK | Main cold review passed |
| `ab200d2c` | authenticated Store-truth read extension, strict Web replica and truthful Task panel projection | Main cold review passed after one test-double compatibility repair |
| `8be8398a` | authenticated committed-voice write path, durable fence/dispatch/reconcile/verifier pump and Web control/recovery | Main cold review passed after the repairs in section 4 |
| `fc7348f2` | D-080 and one-revision showcase/runtime-gate correction | Affected documentation review passed |

Included operations remain only `task.provide_input` and
`task.update_constraints`, with exactly one `1 -> 2` revision. Generic live
steering, same-attempt mutation, decision/approval handling, pause/resume,
reprioritization, preference capture, arbitrary shell, dependency/API/config
changes, commit/push and real user projects remain excluded. The design and
implementation stay within the named Task/Store/Executor/Web modules.

## 2. Applicable Tier 3 scenario matrix

| Dimension | Evidence at reviewed source | Result |
|---|---|---|
| Positive authority | Same task ID advances from revision 1/attempt 1 to revision 2/attempt 2 only after exact confirmation and cleanup ACK. | PASS — deterministic source tests |
| Scope and authentication | Target identity comes from Store authority; wrong scope, stale revision/attempt and forged confirmation reject before mutation. Web reads through existing authenticated `task.status`. | PASS — deterministic source tests |
| Replay and concurrency | Same fingerprint replays, changed fingerprint conflicts, concurrent revisions admit at most one fence and no duplicate successor. | PASS — deterministic source tests |
| Atomicity and restart | Store failpoints roll back each request/apply boundary; schema v1 migrates to v2; reopen preserves revision/execution truth without silent rerun. | PASS — deterministic source tests |
| Cancellation and late facts | Cancel/terminal races create no successor; predecessor late terminal/patch/output is quarantined from current truth. | PASS — deterministic source tests |
| Executor cleanup | Exact running predecessor is fenced; non-cooperative, mismatched or unknown cleanup never receives an ACK and cannot start a successor. | PASS — deterministic source tests |
| Project mutation boundary | Fixture must be trusted, clean, local, no-remote and path-contained; forbidden path, dependency, API, configuration, commit and remote effects reject. | PASS — deterministic source tests |
| Verification truth | Only a registered verifier may run; fail, timeout, fixture mutation and unknown cleanup never become verified success; output is bounded and sanitized. | PASS — deterministic source tests |
| Web projection | Parser is closed-schema and exact-target; replica deduplicates, fences disconnects and rejects lineage/lifecycle rewrites; application and lifecycle are separate. | PASS — 327 frontend tests and production build |
| Feature off | Store extension is not created, bridge inspects no untrusted input, backend reader is not called, Web sends no S8.5 read and adds no S8.5 DOM. | PASS — deterministic source tests |
| Forbidden data/effects | No credentials, raw audio, private runtime paths, arbitrary Agent prose, commit or push result is persisted as S8.5 truth. | PASS — source review; no real-path claim |
| Product write path | Exact P2 voice commit and a later exact voice confirmation bind one Store-derived task/revision/attempt; text revision, wrong hints, duplicate request IDs and missing prerequisites have zero mutation. | PASS — integrated registry, authority, confirmation and Web owner tests |
| Durable product recovery | AgentServer starts one gated recovery pump; delivered successor dispatch is rediscovered after Store reopen, terminal truth is reconciled and verifier ACK is persisted without redispatch. | PASS — deterministic restart test; multi-process ownership is out of this profile |

## 3. Verification

- Cumulative affected backend: all `363/363` collected cases reached `PASSED`
  across revision Core/Store, Bridge/Policy, confirmation, authenticated P3,
  product registry and AgentServer; the new S8.5-only AgentServer owner test then
  passed in a focused `2/2` rerun.
- The Windows pytest process did not terminate after printing `100%` because
  imported third-party background threads remained alive; it was interrupted
  after the final test result. This is a runner-exit limitation, not a clean
  pytest exit-code claim.
- Prior direct project-executor affected regression: `88 passed, 2 skipped`;
  the new full-delivery verifier seam passed in the current revision coordinator
  suite.
- Integrated Web strict compile/bundle/tests: `327 passed`.
- Frontend production `tsc && vite build` with the S8.5 Web gate enabled: PASS,
  `4,641` modules transformed; existing mixed-import, duplicate locale-key and
  large-chunk warnings remain non-blocking and outside this scope.
- Changed Python Ruff (with the file's pre-existing AgentServer `E402` debt
  excluded), `py_compile` and `git diff --check`: PASS.

## 4. Findings and repairs

The cumulative cold review retained the earlier AgentServer test-double repair
and found five product-integration issues before the final commit:

1. confirmation expiry used the submitted commit timestamp; it now uses the
   server clock for issue, validation, consumption, policy and Store admission;
2. fixture-registry loading could classify a missing path inconsistently and
   accept wrong collection types through tuple coercion; it now validates the
   exact non-empty JSON schema and clean fixture at startup;
3. durable verification projected delivered outbox rows as claimed; recovery
   now preserves delivered truth and derives only missing ACK work;
4. revision authority did not require every P2/P3 product prerequisite, and the
   Web selector exposed unavailable legacy mutations when only S8.5 was on;
   backend and UI gates now match the exact product route;
5. a second request ID using the same voice commit could reject and release the
   first pending confirmation; the conflict now has zero effect on the original
   pending origin and has a regression assertion.

No open Critical/High/P2 source finding was identified by the final Main cold
review.

An independent D-074 review did not run because no independent review facility
was available in this execution context. The substitute was a fresh cumulative
diff review plus the affected backend, frontend, build and static checks above.
This limitation is explicit: the reviewed scope remains `PARTIAL`, not Tier 3
closed.

## 5. Remaining integration boundary

The isolated branch now contains the complete code-level product path from an
authenticated committed voice request through confirmation, durable revision,
fence, successor dispatch, terminal reconcile, verifier ACK and Web truth. This
is not a migrated or human-accepted product candidate.

Before S8.5 can close:

1. wait for S8/A3 PASS, migrate only reviewed coherent commits onto its exact
   clean closeout source, and resolve against the resulting code rather than
   this branch's mutable status;
2. complete independent Tier 3 review and migrated cumulative verification;
3. provision the machine-private fixture manifest and complete the real
   Speech/Agent/Executor product path on the disposable no-remote target;
4. run two unchanged rehearsals
   and one complete human product acceptance on the migrated candidate.
