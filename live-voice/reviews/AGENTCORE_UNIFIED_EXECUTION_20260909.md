# Native Realtime unified AgentCore execution plan

**Goal:** Complete the accepted direct reuse, adapter reuse and generic-runtime
downshift, with source-installed AgentCore and working shared capability access.

**Architecture:** Native Realtime owns speech, committed input and presentation.
JiuwenSwarm owns authenticated project/session/model/tool configuration and
product effects. AgentCore owns shared Agent/Team/Goal/Workflow execution and
the generic lifecycle primitives those consumers require. Existing native
owners keep their distinct semantics; no second universal Task state machine
is added around Team, Goal and Workflow.

**Tech stack:** Python 3.11, AgentCore pinned at
`94e10cb6102c36fe78a64547957c0def97299273` plus reviewed source changes,
SQLite, the existing Integrated Web frontend and Native Realtime transport.

**Spec:** User-approved Goal of 2026-09-09;
[D-128](../decisions/DECISIONS.md#d-128-source-installed-agentcore-and-unified-capability-execution),
[stable capability boundaries](../architecture/FULL_SOLUTION_2026-07-30.md#2-产品目标与能力边界).
Current completion credit belongs only to [STATUS](../STATUS.md).

## Constraints and ownership

- Preserve the Responses metadata/ToolCall deep-copy repair. Install from the
  pinned, reviewable source checkout; a package version or downloaded wheel is
  insufficient source provenance. Ordinary dependency sync must use that source.
- One JiuwenSwarm commit for each numbered task. Necessary AgentCore commits are
  paired explicitly; a commit in one repository cannot contain the other's changes.
- Do not copy the rejected September foundation candidate or move the entire
  Task Store into AgentCore. Reuse an existing owner first; extend only a proven gap.
- Preserve exact identity, authorization, admission-before-effect, cancellation
  settlement, replay/restart truth, file-effect plans and presentation ACKs.
- Speech interruption does not cancel detached work, a Task, Team or Goal.
- No provider/model replacement, user-project reset, remote-ref update, production
  deployment or claim of physical hearing acceptance is included.
- Follow root [TESTING](../../TESTING.md). Focused checks at each numbered
  boundary; one final applicable full run and cross-module review. Repeat only
  affected checks after a finding or implementation change.

## Capability and removal decisions

| Capability | Shared authority / integration | Live Voice retained responsibility |
|---|---|---|
| Agent and Tools | Configured JiuwenSwarm Agent using AgentCore DeepAgent, tool registry and execution rails | Trusted committed input, bounded output, exact round cancellation and heard history |
| Team and subagents | Existing TeamManager/Runner and configured member builders | Authorized invocation/interaction and projection of actual member/Team state |
| Goal | Existing GoalManager and Agent goal-control path | Explicit target and operation, actual capability discovery and truthful result |
| Team dynamic workflow | Existing Team/Runner execution and interaction | Authorized selection, parameters, input reply and output projection |
| Core Workflow | AgentCore Runner/Workflow registry; JiuwenSwarm has no current production registration caller | Expose registered capabilities truthfully; Team dynamic workflow does not prove this separate route |
| Native Work | Shared service-owned execution lifecycle with AgentCore primitives; checkpoints retain restart-unknown truth | Speech-specific context and completion presentation |
| Durable Task | Shared command/execution identity and minimal missing generic persistence/effect coordination | Project/Git/file-effect policy, user consent and voice/text translation |

Complete reuse means real configured consumers are reachable through the common
service. Merely relocating files, exposing unused interfaces, enabling unchecked
tools or reporting an unsupported action as successful does not meet acceptance.

## Task 1 — direct reuse and source baseline

Owned files: `scripts/install_agentcore_source.py`, `scripts/sdk_patches/`,
`jiuwenswarm/common/agentcore_source.py`, `pyproject.toml`, `uv.lock`,
`jiuwenswarm/debug_launcher.py`, related dependency/launcher tests and the direct
consumer seams in `server/runtime/agent_adapter` and `server/live_voice`.

- [x] Prepare an isolated pinned AgentCore source checkout, retain the existing
  Responses fix, and record the base/tree/patch identity reproducibly.
- [x] Make install/sync and launcher consume verified source; reject missing,
  changed or mismatched source before starting a new service.
- [x] Audit direct reuse against production consumers. Agent/Tools and Code Agent
  already use AgentCore execution; no equivalent direct replacement was found
  for the product lifecycle owners. Keep those owners until Tasks 2–3 actually
  replace them. Do not manufacture a forwarding layer or remove necessary
  authorization/cancellation/persistence merely to show a deletion in Task 1.
- [x] Run dependency/launcher and affected direct-consumer tests, inspect the full
  scoped diff, record review and create the task's commit.

The [Task 1 evidence](../evidence/AGENTCORE_SOURCE_BASELINE_20260909.md) records
source pairing, scoped checks, review fixes and the honest direct-reuse boundary.

Source installation is Tier 1 (P/N/I/K/X); any execution-lifecycle replacement is
Tier 2 and receives an independent review at this coherent boundary. Tests must
distinguish source origin from version equality and preserve Responses round trips.

The 2026-09-09 independent design check confirmed the direct-reuse conclusion:
`interface_deep.py` already drives configured `DeepAgent.attach_output/send_input`;
`project_code_executor.py` calls the configured Code Agent. `AsyncToolRuntime`
does not yet provide settled cancellation or duplicate-identity rejection, and
the common/controller/team Task managers do not provide the durable command/
outbox/effect contract. Therefore Task 1 claims source installation and verified
existing reuse, with runtime code deletion owned by the actual Task 2–3 cutovers.

## Task 2 — common capability adapter and consumers

Owned seams: `server/runtime/agent_adapter/interface.py`, `interface_deep.py`,
`interface_code.py`, existing Team helpers, and Live Voice
`native_business_contract.py`, `native_business_tools.py`,
`native_business_router.py`, `agent_conversation_runtime.py` and the associated
frontend projection/interaction surfaces only where required.

- [ ] Resolve one configured capability service for text and Native consumers;
  route Agent/Tools, Team, Goal and Workflow to their existing owners.
- [ ] Resolve the canonical Agent owner rather than creating a voice channel's
  separate AgentManager pool. One service holds DeepAgent's single output lease;
  text and voice observe projected events from that owner. TeamManager is already
  a cross-channel singleton keyed by session and must remain the Team owner.
- [ ] Carry principal, session, project, selected model, stable execution target
  and operation revision through admission, commands and observation.
- [ ] Deliver actual input/approval requests and replies through the existing
  permission/interaction owner; advertise only operations that owner supports.
- [ ] Preserve Goal pause as stopping subsequent rounds while the current attempt
  settles. Start/resume through the existing attach/control/consume chain. Bind
  Goal and round commands to the expected identity inside the existing SDK lock,
  including commands originating from text. For permission/ask-user, preserve
  `CHAT_SEND + answers + source=*interrupt` to `InteractiveInput`; an unrelated
  `CHAT_ANSWER` receipt is not proof that input was resolved.
- [ ] Extract SwarmFlow observation from the WebSocket handler into the shared
  service; preserve exact run/correlation for replies and start via the configured
  SwarmflowTool. Its `name/resume_id` variants remain unsupported. Ordinary Core
  Workflow needs explicit registered, schema-bound authorized entries and its
  own session/input-required continuation; never infer them from a tool name.
- [ ] Replace voice-only execution orchestration where the shared adapter takes
  ownership; retain media/confirmation/history and project-effect policy.
- [ ] Test positive cross-channel invocation/control and wrong-scope, stale,
  duplicate, cancellation and feature-off paths; independently review and commit.

This is Tier 3 at the authority/protocol seam. P/N/B/S/T/C/R/I/F/K/X apply.
An approval receipt is not execution completion. A cancelled response cannot
publish late audio or cancel a different execution target.

## Task 3 — minimal generic downshift and retirement

Owned seams: AgentCore public runtime modules selected by the consumer gap;
JiuwenSwarm `native_work_runtime.py`, `native_work_journal.py`,
`persistent_task_core.py`, `task_store.py`, `project_code_executor.py` and their
durability collaborators only for the responsibility being replaced.

- [ ] Implement only gaps demonstrated by Tasks 1–2 in AgentCore's existing
  execution/task owners; export and document the actual reusable API.
- [ ] Wire both configured execution and Live Voice consumers to that authority.
  Preserve compatibility with existing persisted Task/Work records and exact
  cancellation/recovery/effect facts.
- [ ] Remove replaced JiuwenSwarm lifecycle/storage/execution logic and migrate
  unique oracles to the owning runtime tests. Record net production-code changes.
- [ ] Run focused lifecycle/durability and consumer integration tests, independent
  review, paired source identity checks and the task's commit.

This is Tier 3; all scenario dimensions apply to the replaced authority. Fault
tests must prove cancellation settlement, no post-cancel success, no duplicate
effects and truthful unknown outcomes after lost process ownership.

## Final candidate verification

- [ ] Run one complete applicable Python suite, affected frontend test/build and
  static checks; classify any inherited failures using exact source evidence.
- [ ] Review the cumulative diff and source-install/Agent/Task/media seams once.
- [ ] Deploy the clean paired candidate locally after checking active work; run
  automated real browser/Native Provider/Agent/tool scenarios on
  `http://127.0.0.1:5173`, with disposable authorized projects and isolated data.
- [ ] Prove conversation, interruption/recovery, real work/tool result, shared
  text/voice target observation/control, configured Team/Goal/Workflow access,
  failure/retry and terminal notification/ACK. Preserve real failed evidence.
- [ ] Record commands, source commits, results, code reduction and remaining
  limitations in scoped evidence; update STATUS and close Goal only when its
  actual accepted boundary is complete.
