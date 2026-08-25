# OpenJiuwen AgentCore local PR preparation review — 2026-08-25

Status: local review and packaging decision only. No PR has been created, no
remote ref has been updated, the installed OpenJiuwen dependency has not changed,
and no LiveVoice migration or cutover is authorized by this document.

This review applies the accepted
[AgentCore reuse and Hermes comparison scope](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md)
to the isolated AgentCore candidate branch. It records stable capability,
symbol, contract and commit identities rather than LiveVoice source line
numbers.

## 1. Review question and answer

The review asked which local AgentCore candidates should be retained, corrected
or abandoned before preparing upstream PRs.

The answer is:

- retain all ten coherent capability groups listed below;
- retain the two later quality-fix commits, but redistribute their hunks into
  the owning PRs when the series is rebuilt;
- abandon no implemented AgentCore capability group;
- create no new `EXE-05` launch-lease capability: current public Agent/Runner
  invocation is reusable through a thin JiuwenSwarm binding adapter;
- do not merge the 33-commit branch, its roughly 32K added lines, or any local
  preparation implementation into the LiveVoice feature branch;
- do not claim that any candidate is installed, integrated, production-ready or
  ready for remote submission.

The candidates are generic AgentTeams correctness and durability capabilities.
They are potential AgentCore PR content, not LiveVoice product code.

## 2. Exact local baselines

| Fact | Value |
|---|---|
| AgentCore repository | `C:\Users\admin\Desktop\openjiuwen\agent-core-oj-g2-local-base` |
| Candidate branch | `codex/oj-g2-local-base` |
| Candidate HEAD | `50c065dc7fb5e0c21903128d1a033c52968be97e` |
| Historical candidate base | `4f2c29c34899a45cec56a7d765fcc95e4002f60a` |
| Refreshed upstream after read-only fetch | `origin/develop@6390bbf230f4ea2dd7446bc01ee882e6a4413d4c`; ten commits after historical base |
| Current replay drift | 13 candidate-owned paths changed upstream; historical `F_82`/`F_83`/`S_24` document names now collide |
| Local commits over base | 33 |
| Aggregate candidate diff | 73 files; 31,828 insertions; 646 deletions |
| Worktree at review close | clean |
| LiveVoice product baseline | `hx/0812_live_voice_w3@acd873d0e93b2e82424e0d90a650df2c3515c34c` |
| LiveVoice product mutation by this review | none |

The aggregate diff is a preparation workspace. Its size is not a LiveVoice
reduction target and is not a proposed single PR.

## 3. Capability-group disposition

`KEEP / REPLAY` means the capability and its tests/spec are retained, but the
commit group must be rebased or replayed onto the then-current AgentCore
`develop` and reviewed as an independent PR. It does not mean “merge now.”

| Order | Capability and owner | Existing local commits | Decision | Why it remains in scope |
|---:|---|---|---|---|
| 1 | `SCOPE-01`: mandatory TeamTask scope in TaskDao/Manager | `21d8ca94`, `660f3d56`, `ced87a3e` | `KEEP / REPLAY` | Direct reuse is unsafe if a Task ID can cross team authority. This is a generic isolation correction, not Voice policy. |
| 2 | `A1`: monotonic AsyncTool cancellation and callback fencing | `85602c54`, `c248e756`, `5c3ef668` | `KEEP / REPLAY` | LiveVoice must reuse one runtime lifecycle without late spill, injection or reused-ID settlement after accepted cancellation. The contract is useful to every background Tool caller. |
| 3 | `A2` / `EXEC-OWN-01`: durable Task execution ownership | `9b9f1c3b`, `6095e350`, `6551d023` | `KEEP / REPLAY` | Canonical execution identity, owner epoch, generation/profile and CAS settlement belong beside AgentTeams Task authority. LiveVoice must not retain a peer attempt journal. |
| 4 | `ADD-01`: Task command replay and immutable result authority | `4a68fd8a`, `64447e9e`, `55b13458` | `KEEP / REPLAY` | Existing Session/controller state cannot atomically replay scoped TeamTask commands or publish token-fenced immutable results. Product intent and confirmation stay downstream. |
| 5 | `ADD-02`: canonical Task events and dispatch authority | `78b4a36c`, `f401d2a4`, `473ad7cf` | `KEEP / REPLAY` | Task state and launch dispatch need one transaction and recoverable delivery truth. Voice/text presentation is explicitly excluded. |
| 6 | `ADD-05`: execution-checkpoint publication | `5e4355ec`, `30897cd0`, `7c08730f` | `KEEP / REPLAY` | Base Checkpointer can store payload but cannot make it resume-authoritative for an exact TeamTask execution. Product codecs and project payload policy stay in adapters. |
| 7 | `ADD-04`: external-effect journal and continuation fencing | `398454d0`, `bead0a87`, `8f30c02c` | `KEEP / REPLAY` | Generic intent/dispatch/receipt/observation/settlement truth is absent from Workflow Journal and Session VCS. Project/file probes and compensation policy stay downstream. |
| 8 | `ADD-03`: Task-event consumer cursor | `73301660`, `15bd4cbc`, `2cc81078` | `KEEP / REPLAY` | Generic ordered consumers need scoped unread/ACK CAS. DOM adoption, playout and response-generation receipts remain LiveVoice facts. |
| 9 | Bound Task facade plus bound checkpoint seam | `9cc5727e`, `f927f86c`, `a514fe06`, `503cf538` | `KEEP / REPLAY` | `TeamAgent.task_authority` supplies the least-privilege public API needed by a thin product adapter without exposing Manager/DAO. |
| 10 | Bound external-effect facade | `53dfcc7c`, `8db056f5`, `db821683` | `KEEP / REPLAY` | `TeamAgent.effect_authority` separates external-call continuation authority from ordinary Task readers and writers. Reaper/provider/product policy is not exposed. |

The following cleanup commits are retained as review fixes, not as standalone
PRs:

| Commit | Retained correction | Replay rule |
|---|---|---|
| `fbfb4c5f` | Public authority typing, generic checkpoint test identifiers, added-file formatting and explicit asynchronous test terminal paths | Split the hunks among `ADD-01`, `ADD-02`, `ADD-05`, A2 and the bound-facade PRs. |
| `50c065dc` | Typed A1 completion callback and lint-clean existing TaskManager tests touched by the series | Put the callback hunk in A1; put TaskManager test cleanup in the earliest PR that touches that test surface. |

No local history was rewritten during this review. The current commit graph is
evidence from which reviewable PRs can be rebuilt; it is not itself the final PR
stack.

## 4. Public API and ownership decision

The accepted public composition is:

| Consumer need | AgentCore target | Downstream responsibility |
|---|---|---|
| Run foreground Agent or stream results | existing public `Runner.run_agent` / `Runner.run_agent_streaming` and existing Agent bases | authenticate principal/project/session, select the Jiuwen project Agent, translate committed context and stream observations |
| Read/update canonical TeamTask, read events and ACK a generic consumer cursor | `TeamAgent.task_authority` returning `TeamTaskAuthority` | product intent, confirmation, response reservation, DOM/playout and voice presentation policy |
| Store/reload opaque checkpoint bytes | `ExecutionCheckpointCoordinator` over bound `TeamTaskAuthority` | checkpoint codec, project payload store, compatibility and retention policy |
| Journal and invoke one external effect | `TeamAgent.effect_authority`, `TeamExecutionEffectAuthority` and `ExternalEffectCoordinator` | provider credentials, request body, project/file probe, compensation and user confirmation policy |
| Background Tool lifecycle | `AsyncToolRuntime` plus the exact A2 execution token | product timeout/escalation reporting and project resource cleanup |

Important negative decisions:

- no public DAO or Manager is exported as the LiveVoice integration surface;
- no AgentCore API owns Jiuwen principal/project authorization, voice intent,
  speech/media state, browser generation, response reservation, DOM ACK,
  playout ACK, presentation recovery or privacy policy;
- no generic Task cursor is treated as a response/presentation receipt;
- no checkpoint fact or effect prefix mints launch or mutation authority by
  itself;
- no `EXE-05` AgentCore launch-lease PR is prepared. Verified product binding is
  a thin adapter into existing Runner APIs, while A2 owns only Task execution
  admission and settlement.

## 5. Verification evidence

Evidence run against AgentCore candidate HEAD immediately before the review
document was written:

- focused SCOPE/A1/A2/ADD-01..05/public-facade suite: `370 passed`;
- follow-up A1 and existing TaskManager regression after lint cleanup:
  `134 passed`;
- all 16 newly added Python source/test files: Ruff lint clean, Ruff format
  clean, and isolated Mypy (`--follow-imports=skip`) clean;
- every Python file changed by the 33-commit series: Ruff lint clean;
- AgentTeams `compileall`: clean;
- `git diff --check`: clean;
- candidate and LiveVoice product worktrees: clean at the recorded heads.

The downstream
[LiveVoice prototype adjudication](OPENJIUWEN_LIVEVOICE_PROTOTYPE_ADJUDICATION_2026-08-25.md)
then reran all five candidate boundary suites against this exact AgentCore HEAD:
`140 passed`, including five public-facade/file-backed-SQLite integration tests.
The opt-in harness verifies the requested path, exact clean HEAD, import source
and the required capability commits as ancestors. This is cross-repository
compatibility evidence only; it does not install the candidate or select the
large LiveVoice prototypes for integration.

Two repository-wide quality conditions remain explicit rather than hidden:

1. Current Ruff formatting would reformat 17 pre-existing files that the
   candidate series also touches. Formatting them now would create a large,
   mixed mechanical diff. Each rebuilt PR must use the then-current upstream
   formatter and keep any necessary formatting change inside its own surface.
2. Isolated Mypy over all modified production files still reports SQLModel
   descriptor/type-plugin errors in existing and new DAO/model expressions.
   The added pure public modules are clean. Each PR must follow the upstream
   SQLModel typing policy; this review does not suppress the errors or claim a
   repository-wide type-clean baseline.

The two Pydantic V2 class-config deprecation warnings observed during tests are
from existing core client modules and are not introduced by these candidates.

## 6. Proposed PR series

Prepare the PRs in the capability order below. A later PR may be developed in
parallel only after its dependency contracts are fixed; remote submission stays
separately authorized.

1. TeamTask mandatory scope (`SCOPE-01`).
2. AsyncTool monotonic cancellation (`A1`), independent of the durable schema.
3. Durable Task execution ownership (`A2`).
4. Task command and immutable result authority (`ADD-01`).
5. Task events and transactional dispatch (`ADD-02`).
6. External-effect journal and continuation fencing (`ADD-04`), which can be
   replayed directly from the accepted execution/event contracts.
7. Execution-checkpoint publication (`ADD-05`), after selecting reuse of an
   accepted internal effect primitive or a strictly checkpoint-only
   reservation.
8. Task-event consumer cursor (`ADD-03`); it depends on events, not on
   checkpoint/effect, so its review may occur earlier once `ADD-02` is stable.
9. Bound Task authority and checkpoint public seam.
10. Bound external-effect public seam.

The following immutable historical branch refs retain the original PR numbers
and expose ten reviewable stacked diffs. Their physical sequence places PR 06
before PR 07, but that numbering is evidence identity, not replay order. Each
physical base is the preceding stacked review ref; semantic replay dependencies
are defined by the dedicated packets and may therefore execute PR 07 before PR
06. None of these refs has an upstream or remote ref.

| PR | Local candidate ref | Review base | Candidate head |
|---:|---|---|---|
| 1 | `codex/ac-pr01-task-scope` | historical base `4f2c29c3` | `ced87a3e` |
| 2 | `codex/ac-pr02-async-cancel` | `codex/ac-pr01-task-scope` | `5c3ef668` |
| 3 | `codex/ac-pr03-execution-owner` | `codex/ac-pr02-async-cancel` | `6551d023` |
| 4 | `codex/ac-pr04-command-result` | `codex/ac-pr03-execution-owner` | `55b13458` |
| 5 | `codex/ac-pr05-event-dispatch` | `codex/ac-pr04-command-result` | `473ad7cf` |
| 6 | `codex/ac-pr06-checkpoint` | `codex/ac-pr05-event-dispatch` | `7c08730f` |
| 7 | `codex/ac-pr07-effect-journal` | `codex/ac-pr06-checkpoint` | `8f30c02c` |
| 8 | `codex/ac-pr08-event-cursor` | `codex/ac-pr07-effect-journal` | `2cc81078` |
| 9 | `codex/ac-pr09-bound-task` | `codex/ac-pr08-event-cursor` | `503cf538` |
| 10 | `codex/ac-pr10-bound-effect` | `codex/ac-pr09-bound-task` | `db821683` |

These refs intentionally end before the cross-group quality commits
`fbfb4c5f` and `50c065dc`. The aggregate review HEAD proves their corrections,
but each future replay must put the relevant hunk into its owning PR rather than
adding an eleventh cleanup PR. The refs are review views, not submission-ready
branches.

The dedicated test-first replay packets are indexed in
[AgentCore local PR replay packets](agentcore-pr-preparation/README.md). Each
packet names its exact owned source/tests, intended public contract, dependency
order, red/green and compatibility commands, quality-fix ownership, proposed
PR title/body content, risk and exclusions. Their existence closed planning,
not implementation at the time of this review. The live execution state is now
maintained in the packet index; it supersedes the historical `replay pending`
labels recorded here.

The refreshed upstream drift is already material: current `origin/develop`
is `6390bbf2`, and AgentTeams Task storage, session-table DDL,
TeamAgent/Scheduler integrations and documentation identifiers moved after the
historical candidate base. Therefore no review ref may be submitted by merely
changing its base. Replay must preserve upstream session-file hydration and
write-lock DDL behavior, allocate collision-free docs identifiers, and rerun
the affected upstream tests.

Read-only replay preflight is now complete through PR 07. PR 04 must preserve
the accepted execution-quiescence, review-round, Team-tombstone, terminal and
SessionFileStore contracts. PR 05 additionally requires non-cascading
session-domain event/dispatch history, an explicit retired-Task/incarnation
policy, complete Team-clean writer coverage, a declared legacy-stream baseline
and truthful permanent-rejection, accepted-receipt and authorization-expiry
semantics. Its complete atomicity claim also requires an explicit solution or
scope reduction for SessionFileStore writes that currently occur before the SQL
transaction. PR 06 must reject the historical payload-first publication order:
initially invalid callers may not reach the external store. A valid publication
requires exact runtime/phase/incarnation preauthorization, a server-derived
scoped storage key, one-use finalization into reference/event/head truth and a
durable reaper for only post-authorization orphans. Ordinary clean must preserve
checkpoint/source-event tombstones, reads must validate the exact source event
before payload `get`, and raw mutation authority must not escape ahead of the
bound PR 09 facade. The independent PR 06 preflight reports `4 Critical / 2
Important`; its remaining scope freeze must decide whether to reuse PR 07's
accepted effect continuation or own a strictly checkpoint-only reservation.
PR 07's historical continuation is not yet that accepted primitive: CALL ignores
the authorization's current prefix, OBSERVE is repeatable, and CALL/RECONCILE
tokens can append the wrong evidence type without any provider call. Its
projection is not reconstructibly checked against the fact prefix, leaks live
claim tokens, retains stale observation truth across retry and cascades all
effect tombstones on normal Team clean. The independent PR 07 preflight reports
`5 Critical / 6 Important`. Replay must rebuild purpose-specific one-use
authorization/result finalization under exact runtime/phase/incarnation/
provider/prefix authority, pair genesis with a PR 07-owned effect-intent event
appended through the accepted PR 05 canonical Task-event writer as the
journal-external presence anchor, keep raw seams internal until PR 10, and
preserve current DDL/SessionFileStore behaviour. PR 07 can be replayed from
accepted PR 03/05 without PR 06; only its later
accepted internal primitive may be evaluated for checkpoint reuse. None of PR
04–07 has started formal implementation; all remain blocked on accepted,
reviewable dependency tips.

For every PR:

- replay only the capability's implementation, tests and feature/spec updates
  onto the current AgentCore `develop`;
- preserve positive scenarios and explicit wrong-scope/stale-token/replay/
  corruption zero-side-effect tests;
- rerun affected database dialect compilation and actual SQLite transaction/
  restart/concurrency cases;
- obtain a fresh Tier-3 review after replay rather than treating this local
  branch's earlier review notes as transferable approval;
- do not mention LiveVoice as the sole justification; state the generic
  non-Voice capability value and product exclusions;
- do not push or create a remote PR without the user's exact remote-ref
  authorization.

## 7. Remaining preparation work

Before the AgentCore PR packages can be called ready for submission:

- compare each group with the then-current `develop` and resolve upstream API,
  schema and migration drift;
- finish real-issue metadata and reviewable three-commit history packaging for
  the PR 01–03 technical replays already present locally;
- formally replay PR 04–10 on their accepted dependency tips and redistribute
  the two cross-group quality-fix commits into their owning PRs;
- close the formatter/type-policy decisions described above on each branch;
- rerun the focused and affected suites per PR, not only on the aggregate stack;
- produce per-PR summary, risk, dependency, exact test evidence and exclusions;
- independently review public exports and verify that no product-specific
  identifier or policy enters AgentCore.

LiveVoice adapter implementation, dual-write prevention, data migration,
canary, default-on composition, old Store retirement and code deletion remain
future feature-branch work. They are not part of these AgentCore PR packages and
are not authorized by this preparation review.
