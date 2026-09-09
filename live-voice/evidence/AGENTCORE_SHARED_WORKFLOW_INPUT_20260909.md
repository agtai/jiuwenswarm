# Shared Workflow human-input boundary — 2026-09-09

This is scoped Goal evidence, not the final product acceptance. Task 2/3 remain
uncommitted in JiuwenSwarm; this candidate has not been deployed.

## Source pairing

AgentCore `f5039e6013c3bbfddf01a52ce33bc49b2be713f5`
(`feat(swarm): share exact human input ownership across entry points`) descends
from the reviewed output-lifetime source `a3a1aee0`. Its tree is
`60b7c1f503ed23fe3e8eeb6e74ec497763a598c8`. The sixth ordered source patch is
`scripts/sdk_patches/agentcore-swarmflow-reply.patch`.

The pinned installed checkout was fast-forwarded to that commit. Its nine
integrated files were verified against committed bytes, retaining LF source;
the Windows index stat cache was refreshed without a content change.
`scripts/install_agentcore_source.py --check` then passed and resolved the
editable import to this repository's `.deps/agent-core`. No package reinstall,
runtime launch or remote-ref update occurred. Ordered-patch reconstruction will
be checked with the next stable cumulative SDK candidate.

## Owned behavior and review

The SDK exact reply API locates only an existing session/team/run/correlation
and consumes its original Avatar-owned pending Future. It does not initialize
or restore a Team, publish an unacknowledged message as success, or claim business
completion. The caller's synchronous authority guard executes at consumption.
The original Leader Harness now owns one default controller; warm resume keeps
that owner, and controllers with active/paused handles cannot be replaced.

Independent review reproduced a P1: early pause/stop/finalize fencing originally
blocked only the new exact path; a legacy message still consumed the same Future.
Three actual Runner/messager/Avatar cases failed before repair. A closure tied
to the original pool entry and actual run now fences the common consumer,
including already-in-flight messages and handles registered after the fence.
Warm resume of the same entry remains valid; replacement entries cannot revive
an old Future. The reviewer closed this finding and the missing default-controller
production path after inspecting the complete changes and actual SDK entry test.

## Verification evidence

- SDK final affected group: 166 passed; worker-backend regressions: 17 passed.
  The dedicated exact-reply file contains 51 cases. Scoped Ruff and diff check
  passed. Default/explicit Runner streaming reaches the real SwarmflowTool,
  engine, backend and pending Future; activation/LLM formatting are controlled
  test seams, so this does not count as real-provider business completion.
- Shared application service plus real SDK pool/controller/messager/Avatar:
  41 passed. Wrong scope/run/input, duplicate delivery, callback failure and
  pause/stop/finalize have zero forbidden input effects. This used an explicitly
  verified isolated SDK import and isolated test data.
- Web facade/shared RPC/Gateway schema: 9 passed. The facade no longer creates
  an Agent adapter merely to answer a Team input. A payload cannot override the
  authenticated envelope's session.
- Native protocol/tools/context: 121 passed. Only `workflow.reply` carries the
  extra `input_id`; old operations retain their canonical serialized shape.
- Native reply and existing Workflow queries: 20 passed. Native rechecks the
  current activation and project execution grant at actual consumption and
  reports input acceptance, rejection or uncertainty truthfully.

The final four cases use the real public Web facade and Native router against
the same SDK Future: both entry orderings admit exactly one answer, revocation
while Native waits behind the real pool lock has zero input effects, and a
foreign Web session cannot consume the input. Independent review found no
remaining issue in this bounded input path.

Final cumulative source/product checks remain pending. Credential/provider,
physical audio, Task effect and Workflow business-completion acceptance are not
implied by these input-consumption checks.
