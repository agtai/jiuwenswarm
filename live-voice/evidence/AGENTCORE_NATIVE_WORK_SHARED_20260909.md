# Native Work common execution cutover — 2026-09-09

This records the prepared Task 3 working-tree cutover. Task 2 carries its common
service prerequisites and this checkpoint; the runtime replacement itself is
activated by the separate Task 3 commit.

This uncommitted Task 2/3 boundary connects the existing Native Work journal to
the common `SessionExecutionService` and the public configured `web/agent`
facade. Native Work no longer creates its own Conversation Runtime, Harness,
Bridge, synthetic speech response or per-scope Agent cache. Speech delegate
execution keeps its existing contract; Code remains its own configured mode.

The common service retains the actual producer and pin until cleanup finishes.
The formal facade preserves exact committed input/model version, read-only
tools, private SDK child identity and no generated history. A selected Task
result still disables tools. Shared output validation rejects foreign identity,
split tool-control markup, missing/duplicate/error finals and oversized results.
A usable final remains provisional until the actual source has settled.

## Verification and independent review

The first two actual-facade Work tests failed before the new service adapter
existed. Initial integration exposed a missing subscription to Native Work's
cooperative cancellation event; using its existing `control.read_only` seam
closed that gap without a new cancellation mechanism.

Independent review found a P2: normal cancelled producer Tasks could make the
old settlement classifier change confirmed CANCELLED/SUPERSEDED to UNKNOWN,
blocking replacement work. Two actual-facade cases reproduced this. Formal
producers now record normal cancellation as a stream fact and settle the same
Task after cleanup; ordinary Text still propagates cancellation. A third red
case verified that actual cleanup exceptions must remain on that Task and be
classified before reporting successful cancellation. All three then passed,
and the reviewer closed the finding and repair seam.

- Final Work/common formal-output boundary: 27 passed, including fast cancel,
  successful superseding work, delayed cleanup UNKNOWN, cleanup failure UNKNOWN,
  one exact final, replay conflicts, source identity and tool-less output guards.
- Shared formal output/query/adapter group: 105 passed.
- Original speech `native_delegate` and `no_tool_round` regression group:
  8 passed. Scoped Ruff passed; changed-file diff checks passed.
- The already reviewed common stream group had 18 passing cases before the
  formal-only cancellation repair; its ordinary Text branch was preserved.

Tests use the real JiuwenSwarm facade with a controlled lower formal producer.
They verify no generated history writes, exact model-policy metadata and source
cleanup, not fresh real-provider behavior. Final applicable full verification,
real browser/Provider/Agent acceptance and Native Goal/Team/Task capability
closure remain pending under the complete Goal.
