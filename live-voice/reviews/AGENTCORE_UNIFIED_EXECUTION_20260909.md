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

## Active parallel implementation

The user explicitly resumed implementation using the analyzed parallel plan and
authorized updating repository rules where multiple writers are useful. Root
[parallel ownership](../../AGENTS.md#parallel-ownership) now permits concurrent
writers to disjoint assigned files. This allocation activates only the named
current work, not historical workers. Keep one Goal and the three numbered commit
boundaries; Main integrates worker changes within those boundaries.

Prefer this main session with bounded subagents. Use GPT-6 Astra `xhigh` for
shared execution/authority decisions and difficult SDK lifecycle work, and
`high` for adapters, frontend work and scoped independent review. The current
tool capacity is four active agents including Main; rotate finished assignments
rather than treating every row below as a simultaneous worker.

| Owner | Bounded responsibility | Dependency / exclusive boundary |
|---|---|---|
| Main | Configured Agent ownership, Native execution cutover, exact model/permissions/history and shared protocol integration | Own `session_execution.py`, existing central adapters, Native routing/schema and final source pairing |
| Team/Workflow worker | Existing Team/SwarmFlow/Core Workflow capability adapters and dedicated tests | Freeze exact run/input-reply and admission interfaces first; central Team helpers and Native router remain with Main |
| SDK worker | Only demonstrated generic execution/persistence gaps in existing SDK owners, with SDK tests | Freeze the API and compatibility contract first; no second scheduler, wholesale TaskStore move or duplicate settlement helper |
| Frontend worker | Required shared execution/interaction projections, controls and frontend tests | Consume agreed events/targets; do not invent backend authority or treat receipt/EOF as completion |
| Independent reviewer | Completed scoped diffs, cross-entry invariants and acceptance gaps | Read-only; review at coherent boundaries, rotate a free slot |

Start with contract and consumer-gap analysis in parallel; Main then fixes the
shared interface for each ready boundary so independent implementations can
proceed without waiting for every module's design. Keep Task/Work product policy,
effect handling and consumer retirement with Main until their replacements work.
SDK changes needing a mutable installed source use an isolated source checkout
and environment; frontend and disjoint adapter files may share the main checkout
with explicit file ownership. Preserve the current uncommitted source and pinned
SDK patches when preparing worker baselines; plain HEAD omits Task 2/3 work.

Workers run only their scoped checks with isolated mutable resources. Main
integrates returned changes, runs affected consumer checks, removes superseded
code after equivalence, and produces the requested numbered commits. Run one
final applicable full verification/review and coordinated real browser/Provider/
Agent acceptance on the stable paired candidate. Parallelism does not add full
suite runs or independent deployment/installation authority for each worker.

### Current file assignments and admission contracts

Final assembly correction (Task 2, Tier 3): candidate preparation proved that
Core Workflow only had a test-installed dynamic authorizer and empty production
directory. This is a missing connection in the existing registered-workflow
scope, not a new business workflow. The user confirmed that general integration
is sufficient and supplied no particular business definition. Add a typed,
trusted bootstrap through the real service/Server/AgentManager construction;
bind explicitly selected registered SDK cards to current stored session scopes.
Keep original SDK provider registration with the embedding application, current
Web identity and actual permission owner with the Web entry, and the existing
Native principal/project guard with Native. No RPC callback, dynamic import,
new plugin loader, permission grant policy or second execution registry is added.

The Team worker owns `core_workflow_bootstrap.py`, its dedicated tests and the
existing capability directory's atomic batch binding/new-resolution hook. Main
owns Server/Manager/service entrypoints, shared Web session ownership, Web/Native
adapter wiring and public-entry tests. Scope selection, revocation, duplicate
and invalid batch binding, wrong Web user, scope/owner changes during waits,
same-card provider replacement, original resolved-run continuation and startup
failure must preserve exact identity and zero forbidden execution effects.
Cold directory reads instantiate no provider. New resolution rechecks the
original registration before and after SDK waits; retained runs keep their
original instance. Test through real Server/bootstrap/public SDK execution and
strict recovery, then perform one independent review of this assembly correction.
Existing unchanged broad SDK evidence remains valid. Fold the correction into
Task 2 and the already reviewed retirement tail into Task 3 to preserve the
user's three coherent Host commits; final Host broad checks await this closure.

Assembly closure: these production/test writer leases are now returned to Main.
Bootstrap/directory 58 checks, actual startup 4 checks, final affected public
Agent/Core 56 checks and independent intermediate-Task-2 snapshot 9 checks pass
(overlapping selections). Independent review's metadata ABA finding is fixed
and closed. The Core evidence supplement owns exact commands/boundaries; final
Host breadth and real automatic acceptance proceed after local integration.

Task 3 retirement extension (Tier 2, same admission/physical-lifetime boundary):
repository production-call and dynamic-entry inspection found no remaining
consumer of the AgentConversationRuntime facade's `start_turn`, `commit_turn`,
`dispatch_committed_turn` or `_register_legacy_dispatch`. Product P2 uses
`submit_committed_turn`; Native's runtime owner uses the underlying ConversationRuntime
directly. Remove these replaced facade entrypoints and only the admission-ledger
attachment branches whose sole source was that old route. Preserve the underlying
ConversationRuntime, product submission, identity claims, presentation/effect
protocol and Standard P2 behavior. Migrate the legacy fixture scenarios to the
real product submit route without weakening positive, cancel, capacity, stale,
concurrency or duplicate-admission assertions. Harness Native-only passthroughs
and a handle settlement method may be removed only after full consumer checks.
`sdk_work_context_design` exclusively owns `agent_conversation_runtime.py`,
`jiuwenswarm_round_harness.py` and `test_agent_conversation_runtime.py` for this
bounded deletion and affected tests. Main owns source pairing, index and commits;
the remaining shared service/formal validation files are read-only to this worker.
This removes an already replaced Host bypass; it adds no SDK primitive or policy.

Current retirement follow-up: Main owns removal of the now-unused
`NativeWorkControl.observe` and consolidation of identical Native Team/Core
owner/guard preparation. `sdk_work_context_design` receives only
`native_business_contract.py`, `native_business_tools.py` and their existing
tool/contract tests to derive Provider fields from the existing canonical
contract rules. Keep all operation names/order, closed wire validation and
legacy/bound behavior; this is Tier 1 behavior-preserving schema maintenance,
with the existing operation matrix as its oracle. These assignments supersede
the returned Agent-input Host lease; that completed source is now Main-owned.

Latest checkpoint: SDK `ffeb1abc` is installed from source, with twelve ordered
patches, exact tree reconstruction and verified editable import. Agent input,
Team input and the small NativeHarness task-loop compatibility repair are
paired from reviewed isolated SDK commits. The compatibility repair preserves
the task's original metadata when its round is not a Deep ActiveInteractionRound;
it adds no source authority. Its 13 scoped SDK checks and the previously failing
actual Host/public Team paths passed. The complete scoped leases for Agent input,
Team execution, Native retirement and schema maintenance have returned to Main.
Their evidence is linked in STATUS. Main owns the index, paired source and
numbered commits. Task 2's independently executable snapshot is next; final
candidate verification has not started.

- `parallel_team_workflow_analysis`: Host Team and actual Native public execution
  handoffs complete; all consumers stopped and write leases returned.
- `sdk_work_context_design`: SDK compatibility and legacy retirement complete;
  now read-only deployment preparation, with no installation/config/service authority.
- `sdk_swarmflow_reply_impl`: scoped independent reviews complete, including
  the formal-child, Agent reply and Team control repairs and retirement extension.
  Final cumulative integration-seam review remains at candidate closure.

Exact Agent input is a Tier 3 authority/continuation boundary. The real ReAct
counterexample reused an old approval for a new pending tool call with the same
provider ID. Freeze `InteractiveInput.expected_pending_token` plus a trusted
synchronous `before_effect`, with token and bounded SDK-built execution origin
on the original interruption state. Preserve pending state across preparation;
compare, authorize and claim synchronously before handler effects. An optional
trusted `prepare_effect` may await the original work's existing authorization
after normal SDK preparation and immediately before that synchronous section;
it is never serialized or supplied by wire. Stale,
cancelled or denied pre-claim work changes no pending/answer/history/tool state.
Original work/model/permissions/history and Goal attempt survive continuation;
the new physical task has its actual new task ID. The existing queues and
bounded service records own scheduling/replay; no new registry or scheduler.
Legacy SDK calls remain compatible. Native/Web managed replies must use strict
tokens and a retained original binding; restart without that binding rejects.
Acceptance covers real ABA, matching replies, partial-token rotation,
preparation cancellation/revocation, concurrent/re-entrant claims, actual
Deep/Goal provenance and legacy compatibility (P/N/B/S/T/C/R/I/F/K/X).

Main owns the corresponding Tier 3 Native `agent.pending/reply` and Web
`command.agent_input` protocol and frontend adapters. Exact replies carry the
original source binding/task, pending token, actual input ID and original UI
answer array. The Web adapter uses Gateway connection/user identity and stored
session ownership; E2A must retain its existing envelope user_id when converting
to AgentRequest. No new reply work, model selection or permission policy is
created. A managed question's display request_id is unique to its actual pending
generation; `input_id` retains the SDK ID. Stale UI callbacks cannot select a
new question with a reused provider ID, and an old response cannot clear a newer
question. Missing managed selectors reject; legacy unmanaged/Team answers keep
their existing path. Main owns the Native protocol/router tests, new Web entry
tests and frontend input-command tests.

Configured Team public adapters are the same Tier 3 boundary: Native
`team.list/get/start/cancel` and `workflow.start` consume the existing configured
Team scope. The directory reports its actual configuration fingerprint and
current service epoch. Start uses that fingerprint (explicit null only for an
authorized cold owner), and get/cancel require the epoch and exact retained
execution ID. SwarmFlow start takes only the existing tool's script_path-or-script
and optional string args; it dispatches through the actual leader/permission
rails. A launch receipt must contain the actual tool's run/task IDs. Cold
preparation, current-member and later-spawn guards are owned by the Team worker;
Main owns the public protocols, scope admission and tests. Do not silently change
the stored Team mode or replace configured member models with the voice model.

The demonstrated ordinary Team-input gap is included in this Tier 3 boundary:
an optional trusted synchronous `before_effect` travels through the original
Runner/runtime/leader send chain and is checked again by the original supervisor
before sequence allocation, round start, steering or follow-up insertion. Guarded
input supports exactly one explicit `GodViewMessage`; unsupported remote, bus,
operator and interactive routing rejects before delivery. The guard also checks
the original pool slot/session/harness identity. Rejection settles the existing
ACK without input effects; unguarded legacy calls retain their original behavior.
No new queue, runtime owner or execution policy is introduced. Tests cover real
delivery, gate waits/revocation, owner replacement, queue order, invalid callbacks,
observer cancellation and legacy behavior. This seam is separate from exact
Agent pending-input continuation and receives its own paired SDK patch.

Nested exact Agent replies use child tokens already saved on the parent's
canonical interruption state. Missing or mixed saved tokens reject before the
parent claim. The parent receipt proves only its own claim; the actual child
owner then checks its saved token against live child state. A stale child cannot
execute or consume a newer child interruption, but an already claimed parent is
not rolled back and is never reported as completed nested work. The existing
architecture exposes no atomic multi-owner transaction, and this change adds none.

Writers do not consume a changing dependency. SDK and Host APIs are frozen before
cross-tree testing; Main alone commits, integrates, installs and controls services.
The Native Goal/router test lease has returned after 152 focused checks and one
additional actual ACTIVE-resume check. These prove the controlled SDK seam, not
production Deep/Provider or full browser acceptance.

The next execution-binding boundary is Tier 3. An immutable host policy is
attached to actual SDK scheduled work, not inferred from wire metadata or the
request whose reader happens to receive output. The existing service/output
owner retains the binding; persisted contexts contain only a bounded descriptor,
not credentials or callable authority. Missing/closed/stale bindings fail before
model/tool effects; an invalid Goal attempt uses the existing blocked assessment
instead of rescheduling failures. Revalidate Native model version, principal and
project grant at execution. Ordinary text retains its own model/permissions and
generated history, while Native output acquires no heard-history/audio credit.
Source projection alone is not authorization. Verify interleaved text/Goal work,
scope mismatch, delayed execution, stale/restarted bindings, tool rejection,
history isolation and actual shared reader lifetime. No new scheduler or Task
store is included in this boundary.

Native Goal start/resume is part of this Tier 3 shared control boundary. The
closed Native tool directory now has 23 operations: `goal.set` permits a null
ID/revision pair only for creation and requires an exact pair for replacement;
`goal.resume` requires the observed Goal and control revision. Both use the
existing stored Agent/mode/project and shared execution owner, with actual SDK
control-lock admission, immutable work policy and truthful control receipts.
An ACTIVE resume preserves its existing execution binding. Replayed control
receipts reuse the original entry's observed admission; a snapshot without that
observation cannot claim acceptance. Tests cover these positive paths, CAS,
revocation, model drift, closed/wrong ownership and borrowed-reader lifetime.

Core Workflow public execution/continuation is a Tier 3 shared protocol,
authority and recovery boundary within Task 2/3. New Native operations are
`core_workflow.list/get/start/resume`; Web `command.workflows` opts in with
`kind=core`, while the default SwarmFlow path stays compatible. New mutation
requests carry the observed process epoch, exact capability/run/revision and
registered-schema JSON inputs/answers; existing Native canonical action fields
stay unchanged. Only the original shared service producer owns the Workflow
instance, private SDK session and one pending continuation Future. Short control
admissions use the same bounded records without consuming another SDK execution
slot. Exact CAS, original admission replay and old-epoch rejection prevent
duplicate effects; unknown/unsupported checkpoint recovery cannot restart nodes.

Main owns public Web/Native routing/schema/tests and the shared service hooks;
Core and SDK workers own the files assigned above. Web has no existing equivalent
of the Native principal/project grant. Trusted bootstrap must therefore provide
the synchronous `core_workflow_authorizer` for the actual server connection,
stored scope, operation and declared capability permissions. No configured
authorizer fails closed, including empty-directory reads. Wire metadata is not
authorization. Native reuses its existing current grant. Both entries require
the same stored project ID/mode and existing Agent; neither creates another owner.

P/N/B/S/T/C/R/I/F/K/X apply: real Runner start/pending/continue, simultaneous
Web/Native answers, repeated requests, missing/mixed checkpoints, revocation
during proof, full active capacity, cleanup failure, service close/restart, wrong
scope and unchanged legacy entry. No new business workflow, remote registration,
cross-process automatic resume or universal effect sandbox is introduced.
Strict nested/raw-input continuation remains unsupported unless its complete
checkpoint proof is implemented; it must reject rather than restart a subgraph.

Core Workflow's new adapter has a default-empty explicit host capability
directory. It checks exact scope and card/schema identity before provider/Runner
effects, returns actual `WorkflowOutput`, and validates continuation against
actual pending node IDs and registered schemas. Main retains run/revision/replay
ownership and public entry wiring. Controlled test workflows prove the SDK seam;
they do not count as configured production capabilities or business acceptance.

These are Tier 3 identity/lifecycle/authority boundaries under root TESTING;
the positive path must reach the real owner, and rejected/stale inputs must have
zero forbidden execution, tool, history and other-scope effects. Native Work's
first cutover alone does not close Goal/Team/Workflow/Task execution or retirement.

### Pending-human-input consumer boundary

Web/Text and Native will call the same exact existing Team owner. Native gains
`workflow.reply` with the observed run ID, exact pending `input_id` (the SDK
correlation ID), and the user's answer. It is an input delivery operation, not a
new Team/Workflow launch, tool approval abstraction or completion claim. The
existing authenticated activation/project execution grant is rechecked at the
SDK's synchronous consumption point. Speech interruption is not a reply.

The new input field belongs only to this operation. Old v1 operations retain
their closed fields and canonical serialized bytes, preserving journal replay
identity. Tests cover the positive shared owner, stale/foreign/closing inputs,
concurrent Web/Native/legacy delivery, permission revocation and receipt replay.
The SDK's original Leader Harness supplies its missing default controller;
warm resume keeps that same owner and cannot replace handles still in use.

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

The next Goal execution boundary binds Web edit/confirmation snapshots and
Native/text control requests to `goal_id` plus `control_revision`. A stale or
wrong target must cause no output attachment, scheduling, queue discard or
history write. The existing SDK `attach_output()` currently ensures active
Goal work, and detaching even without abort discards pending work; therefore
attach-before-validation is insufficient. Goal set/resume will prepare their
single output lease only after the SDK has validated the target under its
existing control lock. This is a minimal SDK extension of the same Goal owner,
not a new scheduler. The adapter preserves attach/control/consume ordering for
admitted operations and Web clear stops issuing a separate whole-session cancel.
Owned source/tests include GoalManager, DeepAgent's output entry, the existing
Goal protocol adapter, Web Goal controls and Native capability admission.
The same Goal protocol boundary includes Gateway chunk/event serialization:
`goal.confirm_required` must retain the existing Goal identity/control revision
through the real Web serializer, so a rejected create can offer an exact edit.
The existing completed-then-new-Goal journey retains its observed completed
predecessor as an exact CAS target; active/paused/blocked replacements still
require an explicit edit target. Accepted-objective bubbles are created only
after the authoritative set snapshot, retaining the existing busy-turn deferral.
Tier 3 P/N/B/S/T/C/R/I/F/K/X apply; accepted rejected/stale cases require zero
effects, normal Goal execution and existing consumer compatibility must pass.

The shared stream boundary is an application service owned by AgentManager.
Text and Native capability callers use the existing configured facade producer;
the service retains its exact Agent/session/request identity and projects bounded
events. It owns the facade output consumer, not another Agent/Task/Goal state
machine. A stream ending is explicitly not business completion. Text streams
retain their disconnect cancellation behavior; service-retained capability runs
will detach presentation independently. Native list/get observations authorize
before and after reads and cannot create an Agent or claim absent output means
absent work. Wrong-owner, request-conflict, late/slow observer, producer failure,
shutdown settlement and actual facade output/interaction events are Tier 3
oracles. These projections precede the same service's start/resume adapters and
do not close the full execution/interaction boundary on their own.

The [shared output prerequisite evidence](../evidence/AGENTCORE_SHARED_OUTPUT_20260909.md)
records the implemented text producer owner, Native list/get, actual facade and
journal checks, repaired heartbeat race, bounded whole-event projection and
independent review. It also records strict Workflow I/O/corruption handling and
the inherited Windows atomic-write regression exclusion. These are uncommitted
Task 2 prerequisites; the existing services have not been restarted.

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

The [shared Goal prerequisite evidence](../evidence/AGENTCORE_SHARED_GOAL_20260909.md)
records the paired SDK commit, exact source reconstruction, shared get/pause/
clear adapter, scoped tests and three repaired review findings. These adapters
remain part of the uncommitted Task 2 batch; the complete capability/stream
boundary is still pending.

The first implementation boundary extracts existing SwarmFlow observation from
`server/agent_ws_server.py` into `server/runtime/workflow_queries.py` and adds
Native `workflow.list/get` adapters. This is a read-only Tier 3 protocol/authority
seam: the same authorized session owns both queries, targets resolve only inside
that session, missing targets fail, and observation failure is unavailable rather
than an empty successful inventory. Stored checkpoint reads run off the audio
loop; Native rechecks activation authority after the read. It creates no Agent,
Task, Workflow or tool execution. Current wire projection and waiting-human
content remain owned by `server/wire_truncate.py`. Focused oracles belong to
`test_command_workflows_handler.py`, Native business contract/tools/context tests,
and the shared-query/Native authority integration tests. Real execution/controls,
Core Workflow registration and public owner binding remain the following parts
of the same Task 2 commit, not separate completion claims.

## Task 3 — minimal generic downshift and retirement

The retained P2 Harness will also consume the shared `FormalAgentOutput`
validator already used by Native Work/foreground execution. Main owns
`formal_live_voice.py`, `jiuwenswarm_round_harness.py` and the existing Harness
oracles in `test_agent_conversation_runtime.py`. Remove duplicate provenance,
tool-less buffering/control-markup and final/error validation; preserve P2's
existing streaming result-size policy, reservations, lifecycle and cleanup.
This Tier 2 reuse changes no media or admission protocol. Verify plain output,
split control markup zero leakage, invalid identity, duplicate/empty/error
finals, exact cancellation and cleanup; shared-service bounded results remain
covered by their existing oracles.

The next retirement is the Native foreground's duplicate Harness/Bridge request
composition. It will use the same configured public Agent facade and
`SessionExecutionService.start_formal` already used by detached Native Work.
The existing formal child session continues to isolate committed input and
presentation/history policy. The product registry supplies the shared service;
it no longer allocates a separate voice-channel Agent pool for this capability.
Code/Team remain separately configured capabilities and are not relabelled as
the ordinary Agent profile.

This is a Tier 3 execution/cancellation boundary. Main owns the affected portions
of `agent_conversation_runtime.py`, `product_composition_registry.py`, the shared
service's exact formal cancellation operation and their dedicated tests. Existing
speech source/commit admission and replay remain authoritative. A foreground
interruption targets only its actual service entry; an observer disconnect still
does not replay or cancel admitted detached work. Timeouts report timeout without
claiming physical settlement, and composition close must await any still-owned
cleanup. Validate the real common service/facade, wrong admission zero effects,
one final, exact cancellation, slow cleanup, replay and unchanged presentation.
No media, Task effect policy or Core Workflow lifecycle is changed by this cutover.

The next Native execution cutover must address three observed integration seams,
not just add operation names. `DeepAgent.set_goal` can return no new stream when
an existing text reader owns output; retaining only the new command's short
producer would leave the real output tied to text disconnect. Bind retention to
the actual shared output owner and verify text disconnect/speech interruption
cannot cancel admitted detached work. The ordinary facade also persists generated
assistant output, while Native commits heard speech through presentation ACK;
carry trusted per-execution history authority without treating generated text as
heard or suppressing unrelated text history. Finally, ordinary model-name lookup
can fall back; Native must retain exact catalog identity/config version through
the actual scheduled work. Shared SDK work/output ownership, existing Tool
permissions and the durable Native admission journal remain the authorities.

The output-lifetime implementation binds each SDK output lease to its actual
configured-facade producer. A synchronous SDK output-ready hook runs under the
existing admission lock, after exact Goal validation and before scheduling.
Service-retained commands may retain that existing producer only when its Agent,
session and live lease match; a disconnected/cancelling/unobserved owner rejects
admission before Goal effects. Text-only streams retain disconnect cancellation.
The service projects the actual output-owner identity for borrowed streams;
EOF remains separate from business completion. Owned files are the SDK output
entry, `runtime/session_execution.py`, the existing Deep adapter and their focused
cross-entry tests. This is a Tier 3 lifetime/identity seam (P/N/B/S/T/C/R/I/F/K/X):
verify real SDK Goal admission, text detach after retained admission, detach-first
rejection, stale/foreign/unobserved leases, finishing-lease rollover, producer
failure and ordinary-text compatibility. It changes no Native operation schema,
model/permission policy or history acceptance; those must accompany actual
Native execution dispatch before the Task 2/3 cutover can be claimed complete.
The same owned transport boundary includes Gateway client-disconnect commands
and the Gateway/AgentServer connection's global cleanup. Both must cancel only
transport-owned consumers; retained session IDs pass through the existing
AgentManager, facade, SessionManager, Deep adapter and Team stream cleanup.
Explicit user Stop retains its existing Agent control path. Tests include
ordinary unrelated sessions and unknown/missing runtimes, not only dropping
the local Python stream observer.

The physical cancellation boundary now extends the existing SDK
`core.common.background_tasks` module with a bounded settlement wait. Native
Work and the real NativeHarness async-tool runtime consume the same primitive.
It observes the actual task, distinguishes a stop request from task exit, and
never cancels a borrowed task because its observer disappeared. Native Work
retains its durable transitions, predecessor fence, capacity and presentation.
Async tools retain their two-phase protocol; duplicate live IDs are rejected,
unsettled cancellation remains visible, and a late result cannot begin a new
completion injection. SwarmFlow relaunch must retain a failed resume for retry.
This is a Tier 3 lifecycle seam (P/N/B/S/T/C/R/I/F/K/X); its tests include delayed
cleanup, swallowed cancellation, spill-thread settlement, duplicate identity,
observer cancellation and both production consumers. It is a Task 3 prerequisite,
not completion of the shared Agent output service or the durable Task downshift.

The [settlement prerequisite evidence](../evidence/AGENTCORE_TASK_SETTLEMENT_20260909.md)
records the paired SDK commit, real source reconstruction, both consumers,
focused tests and three closed review findings. The complete Task 3 cutover
and its JiuwenSwarm commit remain pending.

Task 2 prerequisite discovered in source: `GoalManager.peek()` calls
`SessionGoalStore.load()`, whose corrupt-record recovery clears session state.
The shared read-only Goal query must not inherit that mutation. The minimal SDK
extension gives the existing store a strict read method and makes the manager's
read-only snapshot use it; normal `load()` recovery remains compatible. Corrupt
state is unavailable, never an absent successful Goal. This Tier 3 persistence
seam is implemented with the adapter prerequisite, paired in the source patch,
and tested for zero writes/notifications/output attachment/Agent creation.
No new Goal store or sidecar is introduced.

Conditional Goal control is the next prerequisite in the same SDK owner:
`revision` fences execution attempts and deliberately stays unchanged during an
in-flight pause/resume. Reusing it as a control CAS would admit stale commands.
Add a persisted `control_revision` (legacy records default to 1), incremented on
status changes, with optional exact Goal/control-revision preconditions checked
under the existing control lock. Preserve the attempt revision and finishing
assessment semantics. Native commands must provide both preconditions; existing
unconditional SDK callers remain compatible. Tests cover stale/wrong identity,
pause/resume ABA, in-flight assessment, legacy state and zero rejected effects.

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
