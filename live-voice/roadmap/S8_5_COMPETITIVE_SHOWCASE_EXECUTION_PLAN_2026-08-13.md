# S8.5 Competitive Showcase execution plan

> Stable isolated plan under D-079. Mutable progress lives only in
> [STATUS.md](../STATUS.md). S8.5 starts from the clean S8 handoff but may migrate
> to the main line only after S8/A3 PASS.

## 1. Common rules

- Milestone/target: post-Alpha S8.5 candidate; target node `S8.5-C` is local to
  this plan and does not alter D-075 A0–A3.
- Track/modules: `P3 / TC, Store, ED, VB, Web`; Risk Tier 3.
- Included: two bounded revision command types, one revision `1 -> 2`, immutable revision ledger, exact
  predecessor fence, clean successor, trusted verifier, truthful Task UI.
- Excluded: generic live steer, same-attempt mutation, decision response,
  pause/resume/reprioritize, preferences, real user projects, arbitrary shell,
  dependency/API/config changes, D1/D2, public deployment and full P3.
- Compatibility bound: revision applies only to original attempt 1 and cannot be
  mixed with `task.retry`; this incubator does not change Alpha retry semantics.
- Development order is dependency order. Feature-off and Alpha profile preserve
  the current behavior with zero new mutation, allocation or dispatch.
- Each module closes with affected tests and cold scoped review. The complete
  candidate receives an independent Tier 3 review/equivalent, cumulative matrix,
  two unchanged rehearsals and one D-071 human acceptance.

## 2. Dependencies and migration rule

The incubation base is the exact clean S8 handoff recorded by STATUS. Original
S8 work continues independently. No incubator commit is evidence for S8 PASS.

After S8 PASS, identify the exact S8 closeout commit, create a clean integration
worktree, and migrate only coherent commits in this order:

1. decision/docs and contract;
2. Core/Store models and persistence;
3. Bridge/Policy/confirmation;
4. Executor fence/successor/verifier;
5. Web projection and feature configuration;
6. integration tests/review repairs.

Resolve migrations against code, not stale branch prose. Do not cherry-pick the
incubator's `STATUS.md` over S8 closeout; rewrite current status after testing.

## 3. Work packages

### S8.5-01 — decision and design checkpoint

- Freeze D-079, this plan, revision contract, acceptance, showcase and claim
  matrix; route them without expanding README/STATUS into catalogs.
- Verify all S8.5 language is post-Alpha and that the broader excluded product
  surface is absent from requirements and claims.
- Exit: links/diff checks pass and contract gives implementable identities,
  transitions, failures, authority and exclusions.

### S8.5-02 — Task Core and Store revision authority

- Add immutable `TaskRevision`, `task_revision`/`expected_attempt_id`, command
  application state, pending fence, atomic successor and replay ledger.
- Preserve existing create/cancel/retry semantics and on-disk compatibility.
- Tests: positive provide/update; replay/conflict; stale/wrong scope; concurrent
  revision; transaction rollback; restart at every saga boundary; late old events;
  flag-off; zero forbidden side effects.
- Exit: Store is the only revision authority and never dispatches a successor
  without exact cleanup ACK.

### S8.5-03 — Voice Bridge, policy and confirmation

- Map only bounded natural-language/structured operations; ambiguity asks for
  clarification, every mutation requires exact confirmation.
- Canonicalize additive facts and allowlisted constraint patches without letting
  the model invent task/revision/attempt identity.
- Tests: committed positive journey, partial/interim zero mutation, ambiguity,
  critical token, stale confirmation, replay, wrong task/scope and unsupported
  operations.
- Exit: VB remains a mapper; Core/Store remains authoritative.

### S8.5-04 — Executor fence and clean successor

- Fence/stop exact predecessor, quarantine/discard its unapplied worktree and ACK
  cleanup identity; start successor from trusted original fixture base.
- Reject dirty/remote/escaping/real project targets and all forbidden mutations.
- Tests: running/blocked predecessor; cleanup timeout/crash/restart; late patch;
  duplicate dispatch; target mismatch; clean successor proof.
- Exit: old attempt cannot affect current project/task truth after revision.

### S8.5-05 — trusted verifier and result ACK

- Add fixture-manifest verifier allowlist with bounded command, timeout and output.
- Return structured execution/diff/verifier facts; no Agent-selected shell.
- Tests: verifier pass/fail/timeout/missing; modified forbidden path; dependency,
  API/config and remote mutations; sanitizer; zero commit/push.
- Exit: success requires authoritative Executor completion and required verifier.

### S8.5-06 — Task Truth Web projection

- Extend the existing Task panel with revision/attempt lineage, command application,
  cleanup, diff, verifier and unknown states.
- Feature-off preserves current DOM/requests/state. Do not add a second task store.
- Tests: projection/order/dedupe; stale old events; reconnect/restart; accessibility;
  Chrome compatibility floor; flag-off; frontend build.
- Exit: UI never infers application, execution or success.

### S8.5-07 — candidate integration and Tier 3 closure

- Run complete applicable D-032 matrix, backend affected/regression suites,
  frontend tests/build/static checks, diff/link/hygiene and disposable real
  Executor fixture.
- Cold-review cumulative diff and all Core↔Store↔Executor↔Bridge↔Web seams; run
  one independent review or record exact substitute/limitation; repair findings.
- Freeze exact source/environment/flag/fixture manifest and run two complete
  unchanged automated rehearsals.
- Exit: no unresolved critical finding, no forbidden side effect, exact source
  remains unchanged and [S8.5 acceptance](../validation/S8_5_COMPETITIVE_SHOWCASE_ACCEPTANCE.md)
  is ready for the user.

### S8.5-08 — human product acceptance

- User runs [S8.5 showcase](../demo/S8_5_COMPETITIVE_SHOWCASE.md) once on the
  frozen candidate after both rehearsals.
- Record PASS/PARTIAL/BLOCKED/FAIL and only claims permitted by the
  [claim matrix](../S8_5_COMPETITOR_CLAIM_MATRIX_2026-08-13.md).
- Exit: PASS closes only S8.5; it does not confer Production or complete-P3 status.
