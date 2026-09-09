# Task 2 — common configured execution and capability adapters

This commit establishes the common configured-Agent execution service and the
Native/Web adapters for the existing Agent, Goal, Team, SwarmFlow and Core
Workflow owners. AgentCore keeps execution, input continuation, output leases,
Goal/checkpoint state and physical task settlement. JiuwenSwarm keeps authenticated
session/project/model/tool configuration, durable product effects and presentation.
It does not add a second universal task scheduler or move the product TaskStore.

Final assembly inspection reopened the Core Workflow startup seam: actual typed
registration/authorization now flows through `_run`, Server and AgentManager,
then both public entries bind the same exact stored capability scope. The
[Core supplement](AGENTCORE_CORE_WORKFLOW_20260909.md#startup-assembly-supplement)
records the real SDK, actual startup and public identity/continuation checks.
No business workflow is required by the user or silently installed by default.

Agent replies use exact pending generations and original User/Goal work. Goal and
Workflow controls retain their actual identity and continuation owner. Configured
Team commands use the original TeamManager/Runner producer and original tool loop;
receipts and stream EOF never prove business completion. Current grants, original
model versions and source-owned history are checked at the real execution seams.

## Source and scoped verification

- Host base: `66833d5ced9203ce54ffa2fcf009d4de380f62a7` (Task 1).
- SDK: `ffeb1abcc5cc0bc72b5c813a3316d4334d39e15f`, twelve ordered source patches,
  tree `6f3826983ea8c15eb182ec7761705fd5058c1235`. The actual installer reconstructed
  this exact tree, and editable source/import verification passed. Windows checkout
  line endings were normalized to the already committed bytes and index metadata
  refreshed; no SDK source/tree change or package replacement resulted.
- [Shared output and strict queries](AGENTCORE_SHARED_OUTPUT_20260909.md),
  [Goal/Web controls](AGENTCORE_GOAL_OUTPUT_20260909.md),
  [output lifetime](AGENTCORE_OUTPUT_LIFETIME_20260909.md),
  [shared Goal execution](AGENTCORE_SHARED_GOAL_20260909.md),
  [work context](AGENTCORE_WORK_CONTEXT_20260909.md),
  [model/permission/history binding](AGENTCORE_HOST_WORK_BINDING_20260909.md),
  [Workflow input](AGENTCORE_SHARED_WORKFLOW_INPUT_20260909.md),
  [Core Workflow](AGENTCORE_CORE_WORKFLOW_20260909.md),
  [Agent public input](AGENTCORE_AGENT_INPUT_PUBLIC_20260909.md) and
  [Team public execution](AGENTCORE_TEAM_EXECUTION_20260909.md) record the relevant
  scoped tests, real SDK seams, limitations and closed independent review findings.
- Frontend Goal/Agent control tests: 15 passed. Package `tsc --noEmit`: exit 0.
  Final production bundle verification remains at candidate closure.

Main exported the staged Task 2 tree
`20016ce12c5f81b20cd66f993b0f16da2bfef51b` to an independent snapshot and asserted
Host imports resolved there while SDK imports resolved to the installed pinned
source. **29 tests passed in 21.89s**: the complete shared formal execution tests,
the previous Native Work implementation's complete module tests, and three actual
P2 submission/replay/capacity scenarios. Only documentation changed after that
snapshot. This verifies the intermediate commit without depending on Task 3's
implementation. The existing Native Work/Harness route deliberately remains in
this commit; its replacement and legacy-facade deletion belong to Task 3.

Main reviewed the complete module diffs and commit split. The independent module
reviews are recorded in the linked evidence; findings received affected tests and
limited re-review. Whitespace checks passed on source/docs; format-patch context
and trailer syntax are excluded from that textual check, with the actual applied
SDK source and exact reconstruction checked separately.

Local snapshot report and source binding:
`.codex_tmp/unified-commit-boundaries/task2-snapshot.html` and
`task2-snapshot.json`. These controlled lower-seam tests do not establish real
Provider/audio acceptance. Task 3, final applicable broad checks, cumulative
integration review, controlled deployment and real-scenario acceptance remain.

The Core startup supplement was also exported independently above this Task 2
tree, retaining the pre-cutover Native Work implementation. Snapshot tree
`71aced78f62482b3227da845c98e3a05b422255c` passed 9 actual startup, both-origin
Workflow execution and ABA identity checks in 28.52 s; Host import resolved to
that snapshot and SDK import to installed `ffeb1abc`. Only documents changed
after this snapshot. The Windows export omitted the unrelated maintainer
documentation cache because of its long paths; production/tests were complete.
Report: `.codex_tmp/core-bootstrap-integration/task2-snapshot.xml` and
`prepared.json`. This closes the updated intermediate commit without importing
Task 3's execution retirement.

## Final verification repairs

Combined Host verification exposed a cancellation race in the managed Team
reader: Python 3.11 `wait_for(queue.get())` can lose an external cancellation
when its child get completes in the same loop turn. The original model had
answered and the Team was idle, but service closure timed out and its reader
and physical producer remained alive. A deterministic real Service-to-reader
probe reproduced this; a timeout context around the original queue get preserves
external cancellation. The ordinary Text reader and SDK are unchanged.

The permanent regression checks exact reader/physical cancellation, producer
finally, waiter removal and unpin. Failed test cleanup now still attempts
Runner.stop. The complete cold/warm Team module and real Native Team/Workflow
entry passed **9 tests in 20.88 s**, with normal process exit. Evidence:
`%TEMP%/team-cancel-final-_a2lw2pq/`. The four repaired files were identical in
Task 2 and Task 3 before this supplement; the repair belongs to Task 2.

The provider catalog also now re-exports the existing Team execution rail name.
Three original strict-xfail AsyncTool oracles now pass with the implemented SDK
settlement/duplicate-identity capability, so their assertions remain and only
the obsolete expected-failure markers were removed. Catalog checks and the full
G1-A conformance module passed **14 tests, 2 xfailed**; the two remaining gap
characterizations are retained. Evidence: `%TEMP%/jhfclosed-8ijsrdxh/`.
Independent cold review of all four changed files found no open issue. Scoped
diff checks passed; the two existing team_helpers Ruff findings also reproduce
on Task 1, with no new finding from this supplement.

## Final test-oracle corrections

The final breadth run exposed two assertions that had not followed the accepted
capability/projection changes. The Native initial catalog now checks the exact
34 bound tools (the original 13 plus Agent 4, Goal 5, Team 4, SwarmFlow 4 and Core
Workflow 4); strict set equality, JSON seed, automatic tool choice and absence
of premature response creation remain asserted. That case and the complete
Native business-tool schema/binding module passed **133 tests in 3.52 s**
(`%TEMP%/native-tools-final-zhya_okw/`). The Task 1 oracle passed unchanged on its
own baseline, so this was a current test omission rather than an old failure.

The shared public Goal test now seeds a nonempty private SDK run context and
asserts that both Text and Native receive the same public projection without
that context, while the SDK retains it. Caller-mutation isolation and zero
execution effects remain checked. The affected actual-SDK case passed **1 test
in 33.37 s** (`%TEMP%/goal-projection-final-kjsyd6h6/`). Both test-only changes
received independent review; production behavior did not change. They are
folded into this numbered commit without repeating an unchanged broad suite.
