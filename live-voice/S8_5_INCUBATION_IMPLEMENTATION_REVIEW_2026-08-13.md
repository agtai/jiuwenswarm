# S8.5 incubation implementation review — 2026-08-13

> Milestone: post-Alpha S8.5 Competitive Showcase incubation
> Stage/node: S8 / A3 remains ready and not started
> Risk: Tier 3 shared Task/Store/Executor authority
> Comparison base: `a53856de0af12e2c1b11e6cc8f2dc0a18150a99a`
> Reviewed product source: `ab200d2c825eee931e6631cdf4199028b23a59ae`
> Disposition: useful isolated implementation is present and deterministic
> affected checks pass; Tier 3 closure remains `PARTIAL`.

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
| Web projection | Parser is closed-schema and exact-target; replica deduplicates, fences disconnects and rejects lineage/lifecycle rewrites; application and lifecycle are separate. | PASS — 326 frontend tests and production build |
| Feature off | Store extension is not created, bridge inspects no untrusted input, backend reader is not called, Web sends no S8.5 read and adds no S8.5 DOM. | PASS — deterministic source tests |
| Forbidden data/effects | No credentials, raw audio, private runtime paths, arbitrary Agent prose, commit or push result is persisted as S8.5 truth. | PASS — source review; no real-path claim |

## 3. Verification

- Cumulative affected backend: `233 passed` across revision Core/Store,
  Bridge/Policy, Executor/verifier, product registry and AgentServer route.
- Direct project-executor affected regression: `88 passed, 2 skipped`.
- Integrated Web strict compile/bundle/tests: `326 passed`.
- Frontend production `tsc && vite build`: PASS; existing mixed-import and
  large-chunk warnings remain non-blocking.
- Changed Python Ruff (with the file's pre-existing AgentServer `E402` debt
  excluded), `py_compile` and `git diff --check`: PASS.

## 4. Findings and repairs

The cumulative backend run found one compatibility issue in the AgentServer
test double: the new startup diagnostic read the registry's S8.5 flag, but the
test double did not expose that read-only property. The test double contract was
updated and the complete 233-test affected run then passed. No open finding was
identified by the final Main cold review.

An independent D-074 review did not run because no independent review facility
was available in this execution context. The substitute was a fresh cumulative
diff review plus the affected backend, frontend, build and static checks above.
This limitation is explicit: the reviewed scope remains `PARTIAL`, not Tier 3
closed.

## 5. Remaining integration boundary

The product read projection exists, but the Bridge/Policy revision command and
Executor coordinator are not yet wired through the authenticated product
composition mutation route. Real committed speech therefore cannot yet execute
the complete product journey through this branch.

Before S8.5 can close:

1. wire the bounded write path without expanding P3alpha or adding a second
   Task authority;
2. add integrated positive, negative, race, restart and flag-off coverage for
   that exact product path;
3. wait for S8/A3 PASS, migrate only reviewed coherent commits onto its exact
   clean closeout source, and resolve against the resulting code rather than
   this branch's mutable status;
4. complete independent Tier 3 review, cumulative verification, two rehearsals
   and one complete human product acceptance on the migrated candidate.
