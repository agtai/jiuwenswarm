# Agent input public adapters — 2026-09-09 checkpoint

Status: PARTIAL. Strict SDK continuation is source-paired and real Host/Native/Web
positive checks have passed. Two independent review findings remain open: the Web
metadata owner race and reporting a lost post-claim receipt as rejected. Main is
repairing these; this checkpoint does not claim their closure, deployment,
Provider/browser audio acceptance or complete business-execution acceptance.

Main owns the closed Native `agent.pending/reply` schema, Web
`command.agent_input`, Gateway envelope identity preservation and frontend reply
adapter. The shared Host and SDK continuation owners are recorded in the active
[execution plan](../reviews/AGENTCORE_UNIFIED_EXECUTION_20260909.md).

The reply carries the observed source binding/task, pending generation, actual
SDK input ID and explicit answer array. Managed question display IDs also bind
the pending generation, so an old button cannot answer a newer question that
reuses the provider's input ID. Web admission uses the existing Gateway user and
connection plus stored session ownership; caller fields cannot install authority.
The original work supplies continuation model, permission and history context.

Earlier public-adapter evidence against the then-uncommitted Main source and SDK
`e3a1f875` (which lacked the new strict input API):

- `npm.cmd run test:goal-controls`: 14 passed, including four managed-input
  cases. The actual hook/store/transport adapter preserves exact selectors,
  rejects stale/incomplete UI callbacks, retains a question after rejection and
  does not close a newer question when an older receipt arrives. Legacy answers
  retain their existing route. This uses a controlled transport, not a real SDK.
- `test_agent_interrupt_public_entries.py`: all 16 test bodies passed; its
  teardown incorrectly prohibited the legitimate short rejected-RPC record.
  After correcting the fixture to require no prepared work/output owner and
  balanced service pins, the affected unobserved-reply case passed again.
- Two Core Web envelope/parameter session-consistency cases passed in the same
  three-case affected rerun. This repairs WebChannel's redundant session field
  without accepting a different target session.
- E2A Gateway normalization: 8 passed, including conversion of the existing
  trusted envelope user ID into AgentRequest.
- Native contract/tool/context group: 181 passed after adding Agent and Team
  operations. These validate wire shape and carrier identity, not actual execution.

## Source pairing and real execution checks

The installed source now includes Agent input commit
`e833aa42f466a48b14ef2794d581ebd3206678d2` and Team input commit
`a88224703284912511abaca7d972c1ec107da899`. The paired tree is
`f9b2ae8047714035122121a1a6da82566f9c70c9`. The 11-patch manifest check passed;
reconstruction under `.codex_tmp/agentcore-eleven-patch-replay-4zbwp06q/.deps/agent-core`
produced commit `e0307d0` with exactly that tree. Source pairing is not deployment.

- Main's strict-mode SDK candidate check: `test_exact_agent_input.py` and
  `test_deep_agent_exact_input.py`, **46 passed in 23.56s**. These use real
  ReAct/Deep pending state, claim, supervisor and continuation paths, including
  old-pending ABA rejection, partial-answer token rotation, async preparation
  failure, same-reader recovery and Goal continuation in the original attempt.
- Shared Host check against the stable Agent candidate: **31 passed in 24.06s**.
  The group contains all 29 `test_shared_agent_interrupt_execution.py` cases and
  two existing formal cleanup/cancellation isolation cases. It verifies original
  model/permission/source ownership, real pending lookup, same-RPC recovery after
  preclaim rejection, concurrent retry with one tool effect, and no second send
  after a real claim whose receipt is lost.
- `test_agent_interrupt_public_execution.py`: **4 passed in 22.56s**. Actual
  Native decoding and Native/Web adapters reach the same real SDK pending owner,
  preserve original work and replay receipts, reject an old cross-entry answer
  when a provider reuses its input ID, and leave pending state untouched on wrong
  project/user rejection. Provider responses and external tool behavior are
  controlled; this is not a live Provider journey.
- Provider-field deduplication derives the existing tools from contract rules,
  removing 21 net production lines. All 34 operation names, directory and required
  field order, and bound/unbound/legacy canonical JSON remained identical. Three
  contract/tool files yielded 220 passes and one pre-existing test-name parsing
  failure; replay of the pre-change catalog reproduced it. The test-only fix and
  snapshot checks then passed in a four-case affected rerun; scoped Ruff passed.

## Public review closure

Independent review found stale stored Web ownership after owner lookup or SDK
preparation waits, and a lost post-claim receipt reported as rejected. The Web
guard now reads the current stored session/user/channel/project/mode at final
admission without an intervening await. The shared helper preserves explicit
`unknown` with exact selectors and no `accepted: false` when consumption cannot
be disproved; the same RPC never resends that answer. The frontend retains the
question and reports the unknown receipt without crediting acceptance.

The first repair verification passed **55 backend tests in 32.69s** across the
Host and two public-entry files, plus **15 frontend controls tests**. Review
then identified a pre-SDK-send retry regression introduced by that repair.
The classifier again covers all preclaim errors, while tracking whether the
SDK call began before declaring consumption unknown. The real pre-send denial
and same-RPC recovery, both public lost-receipt paths, and stored ownership
change during real SDK preparation passed **4 affected tests in 26.47s**.
The limited independent re-review passed with no remaining blocking finding.
These are controlled-provider real-SDK checks, not live Provider acceptance.

Final frontend build/type checks, Main's Task 2/3 commits, cumulative automated
checks and the Goal's real acceptance remain pending.
