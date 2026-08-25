# OpenJiuwen / LiveVoice symbol migration map — 2026-08-24

Status: local evidence map and proposed OJ-G1-MAP classification. It is the
authoritative factual inventory for this review, not an accepted architecture
decision, installed dependency claim, or product-readiness claim.

The later accepted
[AgentCore reuse and Hermes comparison scope](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md)
governs how this inventory is used. In particular, migration, composition,
canary and retirement sequences recorded below are conditional future design
inputs, not the current execution queue, and the candidate implementations on
the isolated preparation branch are not wholesale integration deliverables.

Risk: this document is Tier 0. Any later change to task authority, execution
ownership, durable effects, ordering, cursors, or migration is Tier 3 until the
applicable rules in [`TESTING.md`](../../TESTING.md) prove otherwise.

## 0. 2026-08-25 candidate review update

The earlier A1/A2 working-tree fingerprints and “implement ADD-01..05” wording
below are historical investigation evidence. The current local implementation
fact is the clean AgentCore preparation branch
`codex/oj-g2-local-base@50c065dc7fb5e0c21903128d1a033c52968be97e`,
stacked as 33 local commits over
historical candidate base
`4f2c29c34899a45cec56a7d765fcc95e4002f60a`. A later read-only fetch
observed `origin/develop@6390bbf230f4ea2dd7446bc01ee882e6a4413d4c`,
ten commits ahead. That drift changes thirteen candidate-owned paths and
collides with historical candidate documentation identifiers, so the local
refs are evidence views and must be replayed rather than rebased blindly.

The complete retain/replay/drop decision, commit grouping, verification and PR
order are recorded in the later
[AgentCore local PR preparation review](OPENJIUWEN_AGENTCORE_PR_PREPARATION_REVIEW_2026-08-25.md).
That review supersedes readiness/status statements in this older map; it does
not supersede the symbol ownership classifications.

The separate
[LiveVoice prototype adjudication](OPENJIUWEN_LIVEVOICE_PROTOTYPE_ADJUDICATION_2026-08-25.md)
applies these classifications to the five isolated downstream commits and the
ignored EVT-02 archive. It selects thin future seams and test oracles, not the
current prototype implementations.

Current resolutions that affect this map are:

| Earlier question | Current local candidate decision |
|---|---|
| Public Task facade | `TeamAgent.task_authority` returns a lifecycle-lease-bound capability bundle with explicit reader/command/cursor/checkpoint grants; a public binding is diagnostic, not authority, and no DAO/Manager/raw finalizer is the product API. |
| Public effect facade | `TeamAgent.effect_authority` returns a separate `TeamExecutionEffectAuthority`; generic reaper/provider/product policy is not exposed. |
| Checkpoint link | The bound checkpoint capability first obtains exact PR 06 preauthorization, then writes to a server-derived scoped key and atomically finalizes the only resume-authoritative reference; initially invalid callers never reach the payload Port and public views expose no locator. |
| Effect owner placement | A subordinate `EffectDao` shares the AgentTeams database/session/Task execution boundary. Workflow engine remains business-neutral. |
| Cursor scope | Internal `CursorDao` owns only generic Task-event consumer/channel ACK beside the accepted event reader; PR 09 derives an opaque consumer/channel capability bound to principal, lease and stream incarnation. Callers cannot select another cursor; response closure, DOM adoption and playout remain product facts. |
| Terminal/result vocabulary | `ExecutionOutcome`, immutable `TaskResultRef`, command decisions and token-fenced settlement are local `ADD-01` candidates. |
| Dispatch boundary | `TaskDispatchRecord` plus claim/receipt/release/recovery is the local `ADD-02` candidate beside Task events and Scheduler. |
| Cancellation ordering | A1 monotonic runtime cancellation is composed with A2 quiesce-before-durable-settlement helpers; a reset-before-cancel product path is not accepted. |
| `EXE-05` | No new AgentCore launch-lease PR. Existing public Agent/Runner invocation is reused through a thin authenticated Jiuwen project binding adapter. |
| Physical migration | Still deliberately unresolved and unauthorized while the LiveVoice feature branch is moving. |

All SCOPE/A1/A2/ADD-01..05/facade implementations remain local PR candidates,
not installed AgentCore capability claims. None of their roughly 32K lines is a
wholesale LiveVoice feature-branch deliverable.

## 1. Finding and scope

The latest LiveVoice implementation already uses OpenJiuwen to construct and run
real Agents and Tools, but surrounds that call with a second task/execution/event
authority. Scope, AsyncTool cancellation, and execution-attempt ownership now have
credible local AgentCore candidate contracts. They are candidates only: the
installed dependency has not changed, and LiveVoice remains the production truth
until a gated cutover.

The minimum target is therefore one AgentCore task/execution authority, extended
in its existing owners for the few generic durability contracts it still lacks,
plus thin JiuwenSwarm adapters for verified product identity, project execution,
and Voice presentation. A migration must never write the same Task, Attempt,
Event, Effect, or Cursor fact to AgentCore and `SqliteTaskStore` as peer truths.

Intended behaviour:

- preserve all current positive task/executor/result/presentation outcomes;
- reject wrong scope, stale owner, stale generation/profile, replay conflict, and
  unauthorized mutation with zero forbidden Agent/Tool/file/presentation effect;
- make accepted cancellation wait for execution quiescence before terminal
  settlement or resource release;
- recover from one canonical durable relation after restart;
- retain committed Voice intent and product presentation semantics in
  JiuwenSwarm.

Owned surfaces are this mapping and the necessary route entry in
[`STATUS.md`](../STATUS.md). Explicit exclusions are AgentCore or LiveVoice
production/test changes, dependency-lock changes, database migration, PR/issue
creation, remote-ref updates, and any use of Hermes implementation. This map
contains no source-size measurement, reduction percentage, or implementation-size
estimate.

## 2. Exact baselines and fingerprints

### 2.1 LiveVoice

| Fact | Value |
|---|---|
| Repository | `C:\Users\admin\Desktop\live voice hx` |
| Branch | `hx/0812_live_voice_w3` |
| Local HEAD used | `a630294aeb77b0fa642952b2a1bb90a8da90e44f` |
| Upstream after `git fetch origin --prune` | `origin/hx/0812_live_voice_w3@c31e85ade1a69e934d05bfb9c277568a1238663c` |
| Relationship | upstream-only `0`; local-only `3`; no divergence and no fast-forward needed |
| Worktree at investigation start | clean |
| Required local evidence commits | `2d06fd37822c6a20ac8185fbe7cd3df7900cf4bc`, `ceda4b5b36227554ff316d61e2511828e1d1ddfb`, `a630294aeb77b0fa642952b2a1bb90a8da90e44f`; all reachable from HEAD |

The local HEAD is the latest production implementation fact because it contains
the fetched upstream tip plus the three required local audit/conformance commits.
No alternate worktree was needed.

### 2.2 OpenJiuwen sources

| Input | Branch / HEAD | Tree and diff fingerprint | Worktree facts | Status in this map |
|---|---|---|---|---|
| Base | `origin/develop@4f2c29c34899a45cec56a7d765fcc95e4002f60a` | tree `0aeacb867ba5e022c1a5d37049c127116c223831` | fetched source baseline | `BASE_EXISTING` reference |
| Installed/locked source | `openjiuwen 0.1.16`; source commit `94e10cb6102c36fe78a64547957c0def97299273` | dependency lock unchanged | uv checkout `C:\Users\admin\AppData\Local\uv\cache\git-v0\checkouts\f5ca8852211336f0\94e10cb6` | actual current dependency |
| Scope | `codex/oj-g1-scope@c2e958e74954d65cf3df9bc7b405baf4cfd2eeb2` | tree `90d1a8696b6dc76d3d0ae847bb31cf51126b9809`; staged/unstaged blob `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | clean; commits `759fdf54`, `c6564a59`, `c2e958e7`; upstream base `4f2c29c3` | `SCOPE_CANDIDATE` |
| A1 | `codex/oj-g1-a1-async-tool-lifecycle@4f2c29c34899a45cec56a7d765fcc95e4002f60a` | staged diff blob `6269605b5e95d6d098fa660f805902d2d596e1bb`; unstaged blob `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | four staged files; no unstaged/untracked files | `A1_CANDIDATE`, not committed |
| A2 | `codex/oj-g1-a2@c2e958e74954d65cf3df9bc7b405baf4cfd2eeb2` | base tree `90d1a8696b6dc76d3d0ae847bb31cf51126b9809`; unstaged diff blob `1613a29f562c9196f55cd8f0727c7f46c19cd0c2` | modified working tree plus three untracked files; no staged files | `A2_CANDIDATE`, not committed |

A1 has exactly these staged files and no unstaged or untracked files:

- `openjiuwen/agent_teams/docs/specs/S_20_native-harness-async-tool-framework.md`
- `openjiuwen/agent_teams/harness/AGENTS.md`
- `openjiuwen/agent_teams/harness/async_tools.py`
- `tests/unit_tests/agent_teams/harness/test_async_tools.py`

A2 has exactly these unstaged tracked files and no staged files:

- `openjiuwen/agent_teams/agent/scheduling/scheduler.py`
- `openjiuwen/agent_teams/docs/specs/S_12_schema-data-models.md`
- `openjiuwen/agent_teams/docs/specs/S_22_scheduling-runtime.md`
- `openjiuwen/agent_teams/docs/specs/S_24_task-storage-scope.md`
- `openjiuwen/agent_teams/schema/task.py`
- `openjiuwen/agent_teams/tools/AGENTS.md`
- `openjiuwen/agent_teams/tools/database/engine.py`
- `openjiuwen/agent_teams/tools/database/task_dao.py`
- `openjiuwen/agent_teams/tools/models.py`
- `openjiuwen/agent_teams/tools/task_manager.py`
- `openjiuwen/agent_teams/tools/team.py`
- `tests/unit_tests/agent_teams/test_review_voting.py`
- `tests/unit_tests/agent_teams/tools/test_tool_variants.py`

Its three untracked file fingerprints are:

| A2 untracked file | SHA-256 |
|---|---|
| `openjiuwen/agent_teams/docs/features/F_83_task-execution-ownership.md` | `e5b0868b4651439c69b946c8df995728fda95c336516a0b55e2e40260b92567b` |
| `openjiuwen/agent_teams/docs/specs/S_25_task-execution-ownership.md` | `ad68a49aa943a7b73420e145652b2e328b091f82e51964546569e5beabada5f3` |
| `tests/unit_tests/agent_teams/test_task_execution_ownership.py` | `ff8d8bb92f8f8b8810d22d5073151c5148b59912e17b4342ea16d8a1950ebb1a` |

The candidate worktrees were inspected at their staged/working-tree states and
were not edited, staged, cleaned, switched, reset, or committed.

Here “staged/unstaged diff blob” means the Git object ID produced by hashing the
exact raw `git diff --cached --binary` or `git diff --binary` byte stream. The
empty-diff object is therefore `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`;
untracked files are fingerprinted separately with SHA-256 because they do not
appear in either diff stream.

## 3. Classification rules

Every symbol or explicitly named responsibility segment has exactly one primary
classification in section 7. Grouped rows enumerate all symbols governed by the
same owner and Gate; a listed symbol is not implicitly assigned to another row.

| Classification | Meaning and required outcome |
|---|---|
| `DIRECT_AGENTCORE` | The locked/base AgentCore already exposes the suitable public contract. The row records `BASE_EXISTING`; LiveVoice may later call that precise API and retire duplicate state only after its Gate. |
| `ADAPTER_DOWNSTREAM` | Generic state/logic moves into an existing or minimally extended AgentCore owner. JiuwenSwarm retains only identity/policy/protocol translation. AgentCore is the sole generic truth; adapter output is derived, not independently mutable truth. |
| `AGENTCORE_PR_CANDIDATE` | The required contract exists only on a local SCOPE/A1/A2/ADD/facade candidate, not in the locked/base dependency. It must be replayed and accepted in the smallest existing AgentCore owner before LiveVoice can reuse it. |
| `LIVEVOICE_KEEP` | The responsibility decides Voice turn/response/generation/presentation, ASR/TTS/media/barge-in, committed intent, destructive confirmation, product principal/project/session, product UI/composition, or project-code policy. It is not generic AgentCore truth. |

## 4. Authority boundary and call chain

```text
committed voice/text input
  -> VoiceTaskBridge / product authority (JiuwenSwarm product truth)
  -> thin scope + command adapter
  -> AgentCore TeamTask + execution attempt (one task/execution truth)
  -> transactional AgentCore outbox / scheduler
  -> Runner / AsyncToolRuntime / create_deep_agent (real Agent/Tool execution)
  -> JiuwenSwarm project binding + worktree/effect probe adapter
  -> AgentCore outcome/event/effect settlement
  -> consumer/channel cursor
  -> JiuwenSwarm text DOM or Voice playout/presentation ACK
```

Current production instead creates `SqliteTaskStore`,
`DirectProjectCodeExecutorAdapter`, and `PersistentTaskCore` in
`create_p3_composition_from_environment`. `PersistentTaskCore.drain_outbox_once`
claims LiveVoice outbox rows and calls executor `dispatch`, `cancel`, or `adjust`;
the direct adapter then calls JiuwenSwarm's background code-task stream, whose
Agent manager constructs OpenJiuwen Agents through `create_deep_agent` and whose
runtime invokes OpenJiuwen Runner/Team Runner. Thus the actual Agent/Tool handoff
is already OpenJiuwen, while task/attempt/outbox/event/effect/cursor truth remains
duplicated outside it.

Restart currently has two execution-shaped stores: `SqliteTaskStore` and
`_DirectProjectAttemptJournal`. The target has one A2 Task/execution relation.
JiuwenSwarm may retain project worktree and applied-patch evidence, but it may not
retain an independent execution disposition, generation, owner, or terminal
truth. Accepted cancellation becomes terminal only after A1 quiescence and any
required product-resource cleanup acknowledgement.

## 5. Capability dependency order

| Order | Capability | Why it precedes the next layer |
|---|---|---|
| 1 | Scope key and verified product-to-team mapping | Every read, CAS, event, effect, cursor, and recovery query must be unable to cross team/project scope. |
| 2 | Canonical Task/execution relation and A1 quiescence | Event/effect facts need one attempt identity; cancellation cannot settle while an old continuation can still mutate. |
| 3 | Command/replay/outcome/result extension | Dispatch admission must be tied to one accepted command and one durable terminal/result truth. |
| 4 | Transactional event envelope/outbox and Scheduler admission | Work must not launch without a committed Task/attempt relation, and state must not change without a replayable fact. |
| 5 | D1 checkpoint binding and D2 effect journal | Recovery and external-effect decisions bind to the canonical generation/profile/owner and ordered attempt. |
| 6 | Consumer/channel cursor and ACK | Presentation may advance only over canonical ordered events and must remain class-specific. |
| 7 | Product adapters and physical cutover | Only after conformance, import, quiescence, and canary can duplicate LiveVoice authorities be retired. |

## 6. AgentCore evidence and composition result

| Generic capability | Existing/candidate evidence | Composition checked | Result |
|---|---|---|---|
| Team-scoped Task storage | Scope `TaskDao`, `TeamTaskManager`, Task monitor/manager predicates | DAO + manager + scheduler lookups under `(team_name, task_id)` | Direct Scope candidate; mandatory scope is reusable. |
| Execution identity/admission | A2 `TeamTaskBase.current_execution_id/execution_version`, `TeamExecutionAttemptBase`; `TaskDao.prepare_execution`, `start_execution`, `claim_execution`, `reconcile_execution` | Task row + attempt row + owner/generation/profile/version CAS + restart | Direct A2 candidate. It does not include real launch wiring, command/event/result/effect/cursor truth. |
| Core controller Task vocabulary/state | base `core.controller.schema.task.TaskStatus` includes submitted/working/paused/input-required/completed/canceled/failed/waiting/unknown; `Task` includes outputs, error, metadata; `core.controller.modules.task_manager.TaskManagerState/get_state/load_state`; controller base restores/saves it through Session | controller Task + serializable manager state + Session persistence, compared with TeamTask/A2 | Existing public vocabulary and output container must be reconciled/reused where semantically equal. It is a separate mutable controller owner, lacks TeamTask scope/execution token/command fingerprint/immutable result, and its Session save is not the TaskDao transaction, so it cannot become a peer canonical Task truth. |
| Session VCS | base `core.session.vcs.VersioningBackend`, `LogEntry.event_id`, per-session WAL/snapshot/commit/head, replay and truncation | Session VCS + controller state + TeamTask/A2 + Scheduler | A real durable monotonic per-session WAL exists and must not be ignored. It is session-scoped, rewindable/truncatable, carries generic context/state deltas, and is not atomic with TaskDao admission/outbox; therefore it cannot supply canonical Task EventEnvelope, command replay, effect settlement or consumer cursor without a separately accepted composition. |
| Async Tool lifecycle | A1 `AsyncToolRecord`, `AsyncToolRuntime.launch/_run/_try_set_terminal/_on_task_done/cancel/wait/cancel_all` | duplicate ID + cooperative/hostile cancellation + spill/injection callback fencing | Direct A1 candidate for in-process worker quiescence; it is not restart durability. |
| Agent/Tool invocation | base Agent/Team Runner, NativeHarness, AsyncTool, `create_deep_agent` | current JiuwenSwarm agent factory + runner + project binding | Base invocation is reusable; product binding and stream/result translation remain adapter concerns. |
| Checkpoint/context persistence | base Checkpointer `Storage.save/recover`, Agent/Team/Workflow storage | Checkpointer + A2 execution relation + Workflow Journal | Useful foundation, but no revisioned Task/effect atomic transaction. D1 needs an adapter; D2 still needs a journal owner. |
| Workflow replay | base Workflow `Journal.load/get_cached/use/save/finalize` | completed-prefix replay + A1 + A2 + Session VCS | Workflow Journal is a content-addressed business-neutral call cache/WAL; Session VCS is a rewindable session WAL. Neither proves in-flight external effect disposition/receipt or shares the A2 Task transaction; both are insufficient for D2. |
| Background capacity | base `BackgroundTaskController`, `ConcurrencyGovernor`, TeamScheduler and NativeHarness pause/abort/snapshot seams | in-memory capacity + A1 worker registry + A2 execution relation | Reusable runtime controls, but restart accounting and durable admission still require the A2 relation plus `ADD-02`; product priority stays downstream. |
| Scheduling/admission | base `TeamScheduler` stable scan and A2 token forwarding | TaskDao CAS + Scheduler scan/message dispatch | No state-plus-outbox transaction, durable claim/backoff, or dispatch receipt; generic addition required in existing TaskDao/Scheduler owners. |
| Event/progress | base `WorkflowProgressEvent`, AgentRail/output streaming, Task manager event callbacks and Session VCS WAL | progress payload + controller/TeamTask state + VCS + Scheduler | VCS supplies durable per-session sequence/replay, but not a TaskDao-scoped immutable envelope or state/event/outbox transaction; progress payload/callbacks add no such authority. |
| Read watermark | base `MessageDao.mark_message_read/mark_messages_read` | timestamp watermark + event stream | Timestamp read state cannot represent `(scope, stream, consumer, channel, sequence)` or independent text/voice ACK. |
| Observability | base logging/OpenTelemetry | logs + progress callbacks + restart | Observation is evidence only and cannot become control truth. |

The evidence above is grounded in the current
[`OpenJiuwen reuse audit`](OPENJIUWEN_REUSE_AND_HERMES_VOICE_MIRROR_AUDIT_2026-08-23.md),
[`OJ-G0 packet`](OPENJIUWEN_G0_CONFORMANCE_PACKET_2026-08-23.md), and
[`OJ-G1-A packet`](OPENJIUWEN_G1_A_EXECUTION_OWNERSHIP_CONFORMANCE_PACKET_2026-08-23.md).
Only their OpenJiuwen/AgentCore evidence is used here.

## 7. Complete symbol mapping

The record tables below use the required fifteen fields. `Composition attempted`
names the actual composition ruled in or out; `Retirement Gate` always implies
no same-task dual write and passing positive plus fail-closed/zero-effect tests.

### 7.1 Executor/runtime

#### EXE-01 — execution port state machine

| Field | Required content |
|---|---|
| Capability ID | `EXE-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/executor_port.py` |
| LiveVoice symbol | `ExecutorPortViolation`; `ExecutorState`; `ExecutorStatus`; `ExecutorPort.dispatch/start/cancel/status/_require` and the state-transition segment of `finish` (capability query is `EXE-02`; terminal outcome payload is `TASK-03`) |
| Current responsibility | Defines an in-memory dispatch/start/cancel/finish state machine used as a formal boundary and test model. |
| Authority/data owned | In-memory attempt intent and status only; it is not the production persistent owner. |
| Product coupling | None. |
| Existing AgentCore evidence | A2 `TeamExecutionAttemptBase`, `TaskExecutionRecord`, and `TaskDao.prepare_execution/start_execution/claim_execution`; A1 owns runtime cancellation. |
| Composition attempted | A2 durable relation plus A1 worker lifecycle covers the generic state transitions; retaining this port would duplicate them. |
| Classification | `AGENTCORE_PR_CANDIDATE — A2_CANDIDATE` |
| Target owner/API | `openjiuwen.agent_teams.tools.task_manager.TeamTaskManager` facade over `TaskDao.prepare_execution/start_execution/claim_execution/get_execution/reconcile_execution`. Cancellation must first fence new continuations, await A1 `cancel`/`wait`, and only then call A2 cancel/reset settlement; the candidate `Team.cancel_member` reset-before-runtime-cancel order is not accepted production wiring. |
| JiuwenSwarm Adapter | Map AgentCore attempt disposition/outcome to product `FormalAttemptState`; no writable state machine. |
| Test oracle | Existing `test_task_core.py` transition/replay/cancel tests plus OJ-G1-A cancel/complete, restart, generation-race, and stale-zero-effect cases. |
| Dependencies | `SCOPE-01`, `EXEC-OWN-01`, `ASYNC-01`. |
| Retirement Gate | A2/A1 are integrated, real callers use the token, restart/cancel conformance passes, and no production import references `ExecutorPort`. |
| Confidence/open issue | High; exact public facade naming may change, but `TaskDao` must remain the owner. |

#### EXE-02 — executor capability and profile admission

| Field | Required content |
|---|---|
| Capability ID | `EXE-02` |
| LiveVoice file | `jiuwenswarm/server/live_voice/executor_port.py`; `jiuwenswarm/server/live_voice/executor_capabilities.py` |
| LiveVoice symbol | `ExecutorCapabilities`; `ExecutorPort.capabilities`; `ExecutorCapabilityProfile` and validation/serialization/digest; `TaskExecutionRequirements`; `_compatible`; `ExecutorSelection`; `select_executor` |
| Current responsibility | Canonicalizes executor capabilities, matches task requirements, and freezes the selected profile digest used at admission/recovery. |
| Authority/data owned | Selection result and profile digest; configuration discovery remains outside it. |
| Product coupling | D0/D1/D2 operation names and project executor policy are JiuwenSwarm-specific; canonical profile/generation binding is generic. |
| Existing AgentCore evidence | A2 already accepts and persists an opaque nonempty `profile_digest` plus `generation` in `TeamExecutionAttemptBase` and checks them in prepare/claim/reconcile. Base has Agent/Tool configuration but no equivalent structured selector. |
| Composition attempted | JiuwenSwarm requirement matching and canonical serialization -> SHA-256 digest -> existing A2 opaque digest/generation is sufficient. The current profile vocabulary includes D0/D1/D2, project serialization and project-mutation facts, so moving the value schema upstream would import product policy. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | Existing A2 `TaskDao.prepare_execution(..., profile_digest, generation, ...)`, exposed by `TeamTaskManager.prepare_execution`; no AgentCore profile schema is added by this migration. |
| JiuwenSwarm Adapter | Input: project Task requirements and enabled D0/D1/D2 executor profiles. Output: opaque digest, generation and JiuwenSwarm executor configuration. Matching/serialization stays downstream. |
| Test oracle | Existing capability-selection tests and formal integration tests for exact profile, version mismatch with zero launch, and real carrier. |
| Dependencies | `EXEC-OWN-01`. |
| Retirement Gate | A2 persists/checks the opaque digest, JiuwenSwarm selection is a pure pre-admission adapter, and persisted LiveVoice selection is no longer independently mutable. |
| Confidence/open issue | High for the opaque-digest path. A future cross-provider typed profile remains a separate open design and would require its own five-test AgentCore PR-candidate admission; it may not reuse D0/D1/D2 or project-policy fields as generic vocabulary. |

#### EXE-03 — durable attempt journal

| Field | Required content |
|---|---|
| Capability ID | `EXE-03` |
| LiveVoice file | `jiuwenswarm/server/live_voice/project_code_executor.py` |
| LiveVoice symbol | `_DirectAttempt`; `_DirectProjectAttemptJournal.all_attempts/get/create/start/finish/request_cancel/reserve_completion/recover_expired`; `DirectProjectCodeExecutorAdapter.status` durable-read segment (`heartbeat` liveness is `ASYNC-01`) |
| Current responsibility | Persists a second attempt owner/generation/lease/terminal relation and exposes its durable status. |
| Authority/data owned | Execution admission, owner lease, cancel request, completion reservation and terminal status. |
| Product coupling | Journal state is generic; worker body and project resources are product-specific. |
| Existing AgentCore evidence | A2 Task/execution relation, owner/epoch/version/generation/profile CAS and reconcile. |
| Composition attempted | A2 durable ownership covers this responsibility; A1 supplies the separate in-process lifecycle in `ASYNC-01`. |
| Classification | `AGENTCORE_PR_CANDIDATE — A2_CANDIDATE` |
| Target owner/API | A2 `TaskDao.prepare_execution/start_execution/claim_execution/reconcile_execution` and `TeamTaskManager` settlement. |
| JiuwenSwarm Adapter | A worker factory keyed by AgentCore execution ID calls the project executor body and returns observations; it owns no disposition/lease. |
| Test oracle | OJ-G1-A duplicate-ID, hostile unwind/spill, cancel/complete, restart-owner, mismatch-zero-effect and generation-race tests; project executor restart/capacity/cancel tests. |
| Dependencies | `SCOPE-01`, `EXEC-OWN-01`, `ASYNC-01`. |
| Retirement Gate | One authoritative execution relation survives restart; A1 waits for quiescence; `_DirectProjectAttemptJournal` no longer stores execution state; old continuations cannot settle a reused ID. |
| Confidence/open issue | High. Product cleanup evidence must be split before journal deletion. |

#### ASYNC-01 — background worker identity, cancellation and quiescence

| Field | Required content |
|---|---|
| Capability ID | `ASYNC-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/project_code_executor.py` |
| LiveVoice symbol | `_DirectProjectAttemptJournal.heartbeat` live-owner segment; `DirectProjectCodeExecutorAdapter.has_live_workers`; live-worker/cancellation/continuation segments of `_dispatch/_run_attempt/_heartbeat/_settle_worker/cancel/close`; `_ReleaseOnce`; runtime adjustment spill/callback eligibility |
| Current responsibility | Registers an active execution ID, runs one coroutine, requests cancellation, awaits unwind, fences late callbacks/spill and releases runtime resources once. |
| Authority/data owned | In-process worker identity and quiescence; no restart truth. |
| Product coupling | Worker body, adjustment payload and project cleanup are product-specific; cancellation and continuation fencing are generic. |
| Existing AgentCore evidence | A1 `AsyncToolRecord`; `AsyncToolRuntime.launch/_run/_try_set_terminal/_on_task_done/cancel/wait/cancel_all`; active duplicate fail-closed and reused-ID continuation identity fence. |
| Composition attempted | A1 covers coroutine lifecycle directly. A2 supplies durable owner/generation but cannot wait for coroutine unwind; both are composed without dual ownership. |
| Classification | `AGENTCORE_PR_CANDIDATE — A1_CANDIDATE` |
| Target owner/API | A1 `AsyncToolRuntime.launch`, `get`, `list_all`, `has_running`, `cancel`, `wait`, `cancel_all` and internal monotonic settlement hooks; its live membership is passed to A2 `reconcile_execution` instead of persisted as a peer execution lease. `cancel_all` is cancellation fan-out only, so a quiescent close must subsequently await each accepted task through `cancel`/`wait`. |
| JiuwenSwarm Adapter | Supplies the project Agent/Tool coroutine and typed success/failure/spill callbacks bound to the A2 execution token. |
| Test oracle | OJ-G1-A hostile cancellation/spill, duplicate ID and cancel/complete cases; A1 hostile-cancel, reuse-isolation, wrapper-error and terminal-race unit tests; LiveVoice noncooperative close tests. |
| Dependencies | `EXEC-OWN-01` for durable identity; A1 itself may be validated independently. |
| Retirement Gate | Accepted cancel awaits actual unwind; no late callback, spill, injection or file effect occurs; reused ID cannot be settled by an old continuation. |
| Confidence/open issue | Medium-high. A1 has no timeout/escalation policy and `cancel_all` does not itself await settlement; product shutdown may report retained cleanup without claiming quiescence. The direct replacement assumes one authoritative harness/runtime liveness registry per scoped session; cross-process live-owner discovery would require an explicit re-scope rather than retaining the LiveVoice heartbeat as peer truth. |

#### EXE-04 — result spill, adjustment and terminal callbacks

| Field | Required content |
|---|---|
| Capability ID | `EXE-04` |
| LiveVoice file | `jiuwenswarm/server/live_voice/project_code_executor.py` |
| LiveVoice symbol | `_bounded_chat_final`; `_attempt_result_artifacts`; `_DirectProjectAttemptJournal.accept_adjustment/finish_adjustment/finish/seal_applied_result`; `DirectProjectCodeExecutorAdapter._observe_stream_payload/_consume_adjustment_checkpoint/_reject_runtime_adjustments/_run_attempt/adjust/settle_adjustment`; `ProjectCodeExecutorAdapter.adjust/settle_adjustment` |
| Current responsibility | Converts stream/tool output to bounded result/artifact facts, gates adjustment delivery, and settles result application. |
| Authority/data owned | Current implementation writes adjustment/result/terminal facts into LiveVoice stores and project journal. |
| Product coupling | Chat-final extraction, project patch artifacts, and runtime adjustment policy are product-specific; callback fencing and generic immutable result association are not. |
| Existing AgentCore evidence | A1 suppresses spill/injection/success callbacks after accepted cancel and fences reused IDs. A2 settles an execution but has no immutable result or adjustment/command ledger. |
| Composition attempted | A1 + A2 prevents stale callbacks but cannot persist a scoped immutable result or idempotent adjustment command. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | Generic terminal/result association goes to the TaskDao extension in `ADD-01`; callback eligibility is A1 `_try_set_terminal`. |
| JiuwenSwarm Adapter | Input: OpenJiuwen stream/tool facts and project patch. Output: bounded generic result reference plus product artifact metadata; adjustment translation remains product policy. |
| Test oracle | Existing result/adjust/retry tests; A1 no-spill-after-cancel; new `ADD-01` result replay/conflict and stale-token zero-write conformance. |
| Dependencies | `ASYNC-01`, `EXEC-OWN-01`, `ADD-01`. |
| Retirement Gate | AgentCore owns immutable outcome/result identity and stale/cancelled callbacks have zero Task/result/file side effects. |
| Confidence/open issue | Medium; generic adjustment support may follow command-ledger semantics but project patch application stays local. |

#### EXE-05 — Agent/Tool launch and verified binding

| Field | Required content |
|---|---|
| Capability ID | `EXE-05` |
| LiveVoice file | `jiuwenswarm/server/live_voice/project_code_executor.py`; `jiuwenswarm/server/runtime/agent_manager.py`; `jiuwenswarm/server/runtime/agent_adapter/interface.py`; `jiuwenswarm/server/runtime/agent_adapter/interface_deep.py` |
| LiveVoice symbol | `LegacyProjectTaskService`; `DirectStreamObservation`; `ProjectExecutionBinding.validate`; `ProjectExecutionBindingResolver.resolve`; `DirectProjectCodeExecutorAdapter._dispatch/_run_attempt/cancel/status`; all `ProjectCodeExecutorAdapter.dispatch/cancel/status/_cancel_bound/_status_bound` binding/translation helpers; `AgentManager.get_live_voice_formal_task_agent`; runtime adapter `process_background_code_task_stream`; deep-agent factory call segment |
| Current responsibility | Resolves a task to a live project/model/session Agent, launches the real background Agent/Tool stream, and translates executor status. |
| Authority/data owned | Product binding decides which verified project Agent may run; OpenJiuwen Runner owns the actual invocation; current adapters also duplicate attempt state. |
| Product coupling | Project/model/session validation and JiuwenSwarm Agent-manager lifecycle are product semantics. |
| Existing AgentCore evidence | Base `create_deep_agent`, Runner/Team Runner, NativeHarness and AsyncTool perform real Agent/Tool execution. A2 provides the execution token but explicitly lacks real-caller wiring. |
| Composition attempted | A2 token -> JiuwenSwarm binding -> base Runner/Agent/Tool is sufficient; moving project identity policy into AgentCore would broaden its authority incorrectly. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | A2 execution token passed to base Runner/AsyncTool launch seam; Runner reports facts back to `TeamTaskManager` settlement API. |
| JiuwenSwarm Adapter | Input: scoped execution token plus verified principal/project/model/session. Output: Runner stream observations and bounded result; no Task/Attempt ownership. |
| Test oracle | Real-Agent formal executor integration, wrong profile/version zero-launch, project-binding mismatch, and wrong scope zero Tool/file effect. |
| Dependencies | `SCOPE-01`, `EXEC-OWN-01`, `ASYNC-01`. |
| Retirement Gate | Every real launch obtains and transmits the A2 token, no bypass can launch, and the adapter has no durable execution disposition. |
| Confidence/open issue | High; the AgentCore public launch carrier still needs to be selected. |

#### EXE-06 — project filesystem, worktree and cleanup

| Field | Required content |
|---|---|
| Capability ID | `EXE-06` |
| LiveVoice file | `jiuwenswarm/server/live_voice/project_code_executor.py` |
| LiveVoice symbol | project/git/path fingerprint helpers; `_AttemptOwnershipLock`; `_create_attempt_worktree/_remove_attempt_worktree/_seed_attempt_worktree/_attempt_patch/_apply_attempt_patch`; artifact helpers; `_RetainedAttemptCleanup`; `mark_cleanup_pending/mark_cleanup_resolved`; `_ensure_attempt_cleanup_coordinator/_cleanup_attempt_resources/close`; `AttemptProjectExecutorLease` |
| Current responsibility | Isolates per-attempt code changes, rejects unsafe links, applies a verified patch, and retains cleanup until project resources are quiescent. |
| Authority/data owned | Project filesystem and patch/application evidence; cleanup completion for those product resources. |
| Product coupling | Git repository, worktree, patch, symlink, project root, and Agent-manager lease are JiuwenSwarm code-task policy. |
| Existing AgentCore evidence | Runner/AsyncTool provides execution lifecycle but no JiuwenSwarm project repository policy. A1 can signal worker quiescence; A2 can fence the execution. |
| Composition attempted | A1/A2 + generic Runner cannot safely infer or own project filesystem semantics. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm `ProjectExecutionBinding` and project executor resource adapter, called under an AgentCore execution token. |
| JiuwenSwarm Adapter | This is the retained adapter: token in; verified project worktree/effect observation/result reference out. |
| Test oracle | Existing per-attempt worktree, unsafe-link, patch, non-cooperative cancel, retained cleanup, restart, and D2 crash-window tests. |
| Dependencies | `ASYNC-01`, `EXEC-OWN-01`, `D2-01`. |
| Retirement Gate | Not retired. Only its generic attempt/lease/terminal columns are removed after AgentCore cutover. |
| Confidence/open issue | High. Cleanup acknowledgement must be reported without becoming a second terminal truth. |

### 7.2 Task core and authority

#### SCOPE-01 — mandatory task scope and product identity mapping

| Field | Required content |
|---|---|
| Capability ID | `SCOPE-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/formal_task_models.py`; `jiuwenswarm/server/live_voice/task_core.py`; `jiuwenswarm/server/live_voice/task_store.py`; `jiuwenswarm/server/live_voice/p3_authenticated_composition.py` |
| LiveVoice symbol | `ResolvedTaskContext`; `TaskAuthorizationGrant.authorize`; `AuthorizationContext`; `TaskCore._authorize/_require_task` scope segments; every `SqliteTaskStore` public read/mutation scope predicate; `P3AuthenticatedContext/P3AuthenticatedComposition` scope validation segments |
| Current responsibility | Binds a task command/read to verified principal, project, session, team and route context; enforces scope at store access. |
| Authority/data owned | JiuwenSwarm decides verified product identity; LiveVoice Store currently enforces Task-row scope. |
| Product coupling | Principal/project/session/route proof is product-specific; mandatory team/task predicate is generic. |
| Existing AgentCore evidence | Scope candidate makes `team_name` mandatory for TaskDao/manager/monitor access and rejects cross-team task reuse. |
| Composition attempted | Product verification -> team-name mapping -> Scope TaskDao predicate preserves both authorities without moving principal policy into AgentCore. |
| Classification | `AGENTCORE_PR_CANDIDATE — SCOPE_CANDIDATE` |
| Target owner/API | Scope candidate `TaskDao` and `TeamTaskManager` methods keyed by `(team_name, task_id)`; AgentCore never accepts an unscoped task ID. |
| JiuwenSwarm Adapter | Input: verified principal/project/session. Output: immutable AgentCore team/scope key and task authorization request. It cannot decide Task state. |
| Test oracle | OJ-G0 wrong-team isolation; Scope candidate manager/DAO tests; LiveVoice wrong principal/project/session and stale authorization tests with zero mutation/launch. |
| Dependencies | None; first migration prerequisite. |
| Retirement Gate | All AgentCore reads/mutations require the mapped scope and exhaustive wrong-scope tests prove zero Task/Event/Tool/file effect. |
| Confidence/open issue | High; canonical encoding of product project/session into `team_name` needs a stable documented adapter rule. |

#### EXEC-OWN-01 — Task/execution relation, admission and settlement

| Field | Required content |
|---|---|
| Capability ID | `EXEC-OWN-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/formal_task_models.py`; `jiuwenswarm/server/live_voice/task_store.py` |
| LiveVoice symbol | `FormalTaskState`; `FormalAttemptState`; `AdmissionDisposition`; `ReconciliationState`; `PersistedExecutorSelection`; `PersistentAdmissionRecord`; `PersistentTaskRecord`; `PersistentAttemptRecord`; `AdmissionPolicy`; `SqliteTaskStore._insert_attempt/create/retry/nonterminal_attempts/admission_projection/mark_reconciliation_pending/mark_reconciliation_resolved/resolve_lost_attempt` |
| Current responsibility | Stores canonical Task and current Attempt, freezes profile/generation, admits one active execution, settles terminal state, resets/retries, and reconciles lost owners. |
| Authority/data owned | Task state, current attempt, execution generation/profile, admission disposition and restart reconciliation. |
| Product coupling | Admission priority values and some retry policy are product choices; the Task/execution relation is generic. |
| Existing AgentCore evidence | A2 `TeamTaskBase`, `TeamExecutionAttemptBase`, `TaskExecutionRecord`, `TaskExecutionOpResult`; `TaskDao.get_execution/get_execution_by_id/prepare_execution/_admit_execution/start_execution/claim_execution/reconcile_execution`; `TeamTaskManager.reset/complete/cancel` paths. |
| Composition attempted | A2 dual-row transaction directly supplies the relation/CAS/restart outcome. A1 supplies coroutine quiescence. The current candidate `Team.cancel_member` resets the durable relation before sending runtime cancellation, so that call ordering is not reusable as production composition even though the two owners are. |
| Classification | `AGENTCORE_PR_CANDIDATE — A2_CANDIDATE` |
| Target owner/API | A2 TaskDao methods above and `TeamTaskManager` public facade; preserve one Task row and per-session execution child rows. |
| JiuwenSwarm Adapter | Map product priority/retry request to generic prepare/reset; project executor consumes the returned execution token. |
| Test oracle | OJ-G1-A atomic admission, cancel/complete, restart lost owner, generation race, mismatch zero effect; A2 ownership suite; LiveVoice create/retry/reopen/reconcile tests. |
| Dependencies | `SCOPE-01`. |
| Retirement Gate | A2 is committed/integrated, real launch/control callers carry its token, cancellation uses fence -> A1 cancel/wait -> A2 settle (or proves an equivalent zero-effect protocol), historical execution-ID reuse fails closed, and LiveVoice Task/Attempt writes are quiesced. |
| Confidence/open issue | Medium-high. A2 has only completed/cancelled terminal dispositions; `ADD-01` must close failed/interrupted/unknown/result truth, and cancel ordering must be repaired before cutover. |

#### TASK-01 — legacy in-memory TaskCore

| Field | Required content |
|---|---|
| Capability ID | `TASK-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/task_core.py` |
| LiveVoice symbol | `TaskState`; `AttemptState`; `TaskRecord`; `AttemptRecord`; `DispatchIntent`; `CancelIntent`; Task/attempt transition segments of `TaskCore.mark_attempt_running/finish_attempt/transition_task/_transition_attempt/query/snapshot` |
| Current responsibility | Pure in-memory reference implementation for Task/Attempt transition and dispatch/cancel intent semantics. Command, event and scope segments are classified separately in `TASK-02`, `EVT-01` and `SCOPE-01`. |
| Authority/data owned | Test/demo-only memory state; production P3 uses `PersistentTaskCore` and `SqliteTaskStore`. |
| Product coupling | None material. |
| Existing AgentCore evidence | Scope + A2 owns the same canonical Task/execution relation; command/event/scope segments are outside this record. |
| Composition attempted | Keeping the model beside AgentCore would be a third state machine and supplies no production durability value. |
| Classification | `AGENTCORE_PR_CANDIDATE — A2_CANDIDATE` |
| Target owner/API | A2 TaskDao `prepare_execution/start_execution/claim_execution` and `TeamTaskManager.reset/complete/cancel`; test-only pure transition helpers may be rewritten against that canonical contract, not retained as authority. |
| JiuwenSwarm Adapter | None beyond product command translation. |
| Test oracle | Port unique Task/Attempt positive transition, competing terminal and cancel-ack tests to AgentCore conformance before retirement; replay/conflict/event tests close under their separate records. |
| Dependencies | `EXEC-OWN-01`. |
| Retirement Gate | Every unique invariant is covered against the installed AgentCore seam and production has no imports. |
| Confidence/open issue | High; verify whether any developer-only sample intentionally depends on the in-memory port. |

#### TASK-02 — command idempotency, controls and mutation preconditions

| Field | Required content |
|---|---|
| Capability ID | `TASK-02` |
| LiveVoice file | `jiuwenswarm/server/live_voice/formal_task_models.py`; `jiuwenswarm/server/live_voice/task_core.py`; `jiuwenswarm/server/live_voice/task_store.py`; `jiuwenswarm/server/live_voice/persistent_task_core.py` |
| LiveVoice symbol | `TaskCommandDisposition`; `TaskMutationDisposition`; `TaskRetryProductRequestFingerprint`; `TaskRetryPrecondition`; `TaskMutationPrecondition`; `TaskRetryAuthoritySnapshot`; `AppliedTaskRetryReplay`; `command_result_extensions`; `TaskCommand.fingerprint`; `TaskCommandResult`; command/replay segments of `TaskCore.execute/_create/_cancel/_retry/_validate_command`; Store `create/create_successor/update/reprioritize/decide_unsupported_control/adjust/cancel/retry/_command_replay/_insert_command/_mutation_fingerprint/_retry_fingerprint`; `PersistentTaskCore.execute` command routing |
| Current responsibility | Deduplicates commands by scoped identity/fingerprint, rejects conflicts/stale preconditions, and records deterministic mutation results. |
| Authority/data owned | Command acceptance/replay, business decision, and mutation precondition truth. |
| Product coupling | Specific update/reprioritize/adjust/successor vocabulary is product-facing; scoped command replay and CAS are generic. |
| Existing AgentCore evidence | A2 execution version/owner CAS and Task settlement; base TaskManager events. No command ledger, payload fingerprint, replay result, or generic stale-precondition record exists. |
| Composition attempted | A2 version CAS + Workflow Journal only handles execution/workflow replay; it cannot replay a Task command result or detect same-ID/different-payload conflicts. |
| Classification | `AGENTCORE_PR_CANDIDATE` — detailed as `ADD-01` |
| Target owner/API | Extend TaskDao/`TeamTaskManager` with scoped `TaskCommandRecord`, `apply_command(command_id, fingerprint, expected_task_version, operation)` and deterministic replay result in the same transaction as Task mutation. |
| JiuwenSwarm Adapter | Translate product command types/payloads to the generic operation; retain product-specific unsupported-control and confirmation policy. |
| Test oracle | Existing persistent-core create/update/control/successor/adjust/retry replay/conflict tests; new AgentCore same-ID/same-payload replay and same-ID/different-payload zero-effect cases. |
| Dependencies | `SCOPE-01`, `EXEC-OWN-01`. |
| Retirement Gate | `ADD-01` conformance passes and AgentCore ledger is the only command truth; no copied command rows remain writable. |
| Confidence/open issue | High for ledger; medium for which product controls become generic operation kinds. |

#### TASK-03 — terminal outcome and immutable result

| Field | Required content |
|---|---|
| Capability ID | `TASK-03` |
| LiveVoice file | `jiuwenswarm/server/live_voice/executor_port.py`; `jiuwenswarm/server/live_voice/formal_task_models.py`; `jiuwenswarm/server/live_voice/task_store.py` |
| LiveVoice symbol | terminal outcome payload segment of `ExecutorPort.finish`; `ExecutorResolution`; `TaskResultAvailability`; `TaskResultArtifact`; `TaskResultRecord`; `ExecutorObservation`; `ExecutorDeliveryResult`; Store `apply_observations/_apply_observation/task_result/consumer_task_result/_task_result_for_row/_reject_open_adjustments_before_terminal/_settle_cancel_command_results` |
| Current responsibility | Applies fenced executor observations, determines completed/failed/cancelled/interrupted/unknown outcome, and stores immutable result/artifact references. |
| Authority/data owned | Terminal outcome, result availability/digest/artifact metadata and observation-to-state settlement. |
| Product coupling | Artifact types and user-facing result projection may be project/product-specific; terminal outcome and immutable references are generic. |
| Existing AgentCore evidence | Base controller `TaskStatus` already has failed/canceled/paused/input-required/unknown vocabulary, and controller `Task` has outputs/error/metadata persisted through `TaskManagerState` and Session. A2 has completed/cancelled settlement and attempt dispositions; A1 fences callbacks. None provides a token-fenced immutable TeamTask result. |
| Composition attempted | Controller Task/Session persistence can restore mutable controller output but is a different owner with no TeamTask scope/execution token or atomic command/settlement transaction. A1 + A2 can select one terminal callback but cannot persist/replay an immutable result. `ADD-01` must reconcile existing status names rather than invent gratuitous synonyms. |
| Classification | `AGENTCORE_PR_CANDIDATE` — part of `ADD-01` |
| Target owner/API | Extend A2 execution row/`TeamTaskManager` settlement with `ExecutionOutcome`, immutable `TaskResultRef`, and token-fenced `settle_execution(execution_token, outcome, result_ref)`. |
| JiuwenSwarm Adapter | Convert chat final/project patch/tool facts into bounded result/artifact references and product display data. |
| Test oracle | Existing result projection, terminal ordering, stale observation, retry-readiness and applied-artifact tests; new restart/replay/immutable-conflict and stale-token zero-write conformance. |
| Dependencies | `EXEC-OWN-01`, `ASYNC-01`. |
| Retirement Gate | AgentCore can represent every current terminal outcome/result, one settlement wins, and product artifact storage cannot mutate Task truth. |
| Confidence/open issue | High. Artifact payloads should stay opaque references, not become an AgentCore project-file schema. |

#### TASK-04 — transactional outbox and Scheduler dispatch

| Field | Required content |
|---|---|
| Capability ID | `TASK-04` |
| LiveVoice file | `jiuwenswarm/server/live_voice/formal_task_models.py`; `jiuwenswarm/server/live_voice/task_store.py`; `jiuwenswarm/server/live_voice/persistent_task_core.py` |
| LiveVoice symbol | `OutboxKind`; `OutboxState`; `PersistentOutboxItem`; Store `_insert_outbox/claim_outbox/defer_admission/release_outbox/reject_outbox/complete_outbox/reset_expired_outbox_claims`; `PersistentTaskCore.drain_outbox_once/drain_outbox/reconcile/reconcile_status`; `FormalExecutor` protocol |
| Current responsibility | Atomically records work beside Task/Attempt mutation, durably claims it, dispatches/cancels/adjusts, retries failures, and reconciles executor status. |
| Authority/data owned | Dispatch admission, outbox claim/lease/order, delivery result and reconciliation-required state. |
| Product coupling | Concrete executor adapter and priority policy are product choices; transactional Task-to-work handoff is generic. |
| Existing AgentCore evidence | Base TeamScheduler scans and dispatches; A2 atomically admits Task/attempt and forwards review tokens. It has no transactional outbox, durable work claim/backoff, or delivery receipt. |
| Composition attempted | A2 transaction followed by TeamScheduler message dispatch still has a crash gap; Scheduler followed by TaskDao update can launch unauthorized work. Logs/Workflow Journal do not close it. |
| Classification | `AGENTCORE_PR_CANDIDATE` — detailed as `ADD-02` |
| Target owner/API | Extend TaskDao transaction with `TaskDispatchRecord`; extend TeamScheduler with `claim_dispatch/complete_dispatch/release_dispatch` using the A2 execution token. |
| JiuwenSwarm Adapter | Map claimed generic dispatch/cancel/adjust record to project Runner/AsyncTool call and return a bounded delivery observation. |
| Test oracle | Existing outbox claim/order/backoff/reopen/reconcile tests; new crash-after-commit-before-send, crash-after-send-before-ACK, wrong-token zero-launch and multi-team isolation conformance. |
| Dependencies | `SCOPE-01`, `EXEC-OWN-01`, `ADD-01`. |
| Retirement Gate | State plus dispatch record commits atomically, one scheduler claim launches, restart safely reclaims, and LiveVoice outbox is no longer writable. |
| Confidence/open issue | High. Cross-process delivery semantics must be chosen without embedding a JiuwenSwarm transport. |

#### TASK-05 — durable recovery facts and D1 checkpoint binding

| Field | Required content |
|---|---|
| Capability ID | `TASK-05` |
| LiveVoice file | `jiuwenswarm/server/live_voice/durability_checkpoint.py`; `jiuwenswarm/server/live_voice/durability_identity.py`; `jiuwenswarm/server/live_voice/durability_readers.py`; `jiuwenswarm/server/live_voice/durability_recovery_facts.py`; `jiuwenswarm/server/live_voice/task_store.py`; `jiuwenswarm/server/live_voice/persistent_task_core.py` |
| LiveVoice symbol | `D1Checkpoint`; `DurabilityProfileBinding`; `DurabilityReadBinding`; `VerifiedCheckpointPrefix`; `verify_checkpoint_prefix`; `ExecutorRecoveryFacts`; Store checkpoint/read/recovery-lineage methods; `PersistentTaskCore.recover_durable_attempt` |
| Current responsibility | Canonicalizes authority-free checkpoint/recovery facts, verifies bounded prefixes and binds resume to scope/profile/generation/owner. |
| Authority/data owned | LiveVoice Store currently owns checkpoint sequence and recovery authorization; fact objects explicitly own no mutation/executor authority. |
| Product coupling | Project checkpoint bytes and D0/D1/D2 capability profile are JiuwenSwarm executor semantics; monotonic checkpoint association is generic. |
| Existing AgentCore evidence | Base Checkpointer `Storage.save/recover` and Agent/Workflow storage; A2 execution relation/profile/generation/owner; no atomic revisioned Task/checkpoint API. |
| Composition attempted | A2 token + base Checkpointer can address the generic record, but Checkpointer data alone cannot authorize Task mutation or executor invocation. |
| Classification | `AGENTCORE_PR_CANDIDATE` — detailed as `ADD-05` |
| Target owner/API | Extend the A2 TaskDao execution owner with an immutable checkpoint reference/head and exact canonical source event. TaskDao first validates runtime/phase/incarnation and persists a one-use publication authorization with a server-derived scoped key; only then may the payload Port write bytes, and exact token finalization atomically publishes reference/event/head truth. |
| JiuwenSwarm Adapter | Encode/decode project D1 checkpoint and supply product capability/profile binding; verified facts remain authority-free inputs. |
| Test oracle | Existing checkpoint prefix/corruption/profile/generation/reopen/recovery tests and OJ-G1-A mismatch-checkpoint zero-effect cases; new initially-invalid zero-`put`, crash-before/after preauthorization/payload/finalize, source-event corruption-before-`get`, scoped-key collision, tombstone replay and stale-reference zero-launch conformance. |
| Dependencies | `SCOPE-01`, `EXEC-OWN-01`, `ADD-02`; D2 paths additionally require `D2-01`. |
| Retirement Gate | `ADD-05` Tier-3 conformance passes; resume authority is minted only after TaskDao validates canonical execution plus verified Checkpointer prefix; stale/mismatched or unreferenced input has zero launch/mutation. |
| Confidence/open issue | Medium; choose reuse of the accepted `ADD-04` one-use continuation or a strictly checkpoint-only reservation, with durable bounded reaping for post-authorization orphans. Payload-first publication and caller-chosen shared-store identity are rejected. |

#### STORE-01 — LiveVoice SQLite engine, schema and legacy migrations

| Field | Required content |
|---|---|
| Capability ID | `STORE-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/task_store.py` |
| LiveVoice symbol | `SqliteTaskStore.__init__/_connect/_transaction/_reader/_snapshot_reader/_initialize/_enable_wal_journal_mode`; metadata/structure/semantic verification helpers; `_create_schema_v6`; `_migrate_v1_to_v2/_migrate_v2_to_v3/_migrate_v3_to_v4/_migrate_v4_to_v5/_migrate_v5_to_v6`; `_normalize_legacy_candidate_v6`; `_verify_database/_verify_v4_lineage/_verify_v4_semantics/_verify_v5_semantics/_verify_v6_semantics` |
| Current responsibility | Creates, migrates and verifies the parallel LiveVoice SQLite schema and supplies its transaction/read boundaries. |
| Authority/data owned | Physical storage for the current LiveVoice Task/Attempt/Command/Event/Outbox/Result/Cursor/Checkpoint/Effect authorities. |
| Product coupling | Database path/configuration and old schema lineage are JiuwenSwarm deployment/migration facts; generic durable owners should live in AgentCore business storage. |
| Existing AgentCore evidence | Base AgentTeams database engine, SQLModel schemas and TaskDao; A2 extends `tools/database/engine.py`, `tools/models.py` and TaskDao with execution-attempt storage. `ADD-01..05` must extend that same business-storage boundary. |
| Composition attempted | AgentCore storage can become the sole target; copying LiveVoice schema/migrations upstream would preserve a parallel authority. Old lineage is useful only to a later quiesced importer/rollback reader. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | AgentTeams `openjiuwen.agent_teams.tools.database.engine`, existing models/TaskDao, and the accepted additions. A later JiuwenSwarm migration adapter reads verified legacy v6 data and writes only through the AgentCore facade. |
| JiuwenSwarm Adapter | Read-only, version-checked import/rollback adapter for the legacy database; no live dual write and no migration is implemented by this map. |
| Test oracle | Existing schema create/reopen/corruption/legacy-version/fail-closed tests; later import rehearsal proves record counts/identities/digests semantically without treating old rows as live truth. |
| Dependencies | All target authority schemas; physical work is deferred to `OJ-G1-CUTOVER`. |
| Retirement Gate | Quiesced import, verification, canary and rollback window complete; all old writers disabled before schema/wrapper removal. |
| Confidence/open issue | Medium. Import topology and rollback window remain a separately authorized migration decision. |

### 7.3 Event, result and presentation

#### EVT-01 — scoped ordered EventEnvelope and replay

| Field | Required content |
|---|---|
| Capability ID | `EVT-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/formal_task_models.py`; `jiuwenswarm/server/live_voice/task_core.py`; `jiuwenswarm/server/live_voice/task_store.py` |
| LiveVoice symbol | `PersistentTaskEvent`; `TaskEventAuthoritySnapshot`; `TaskEvent`; `TaskCore._append_event` and `project_work_progress` envelope/projection source segment; Store `_insert_event/_append_event/events/consumer_events/_events/events_page/event_authority_snapshot/consumer_event_authority_snapshot/_event_authority_snapshot` |
| Current responsibility | Persists immutable scoped Task events with identity/sequence/causation and returns ordered replay plus an atomic authority head. |
| Authority/data owned | Event identity, per-task/stream order, payload, producer/causation and durable event head. |
| Product coupling | Specific event payload/projection is product-facing; envelope, ordering and replay are generic. |
| Existing AgentCore evidence | Base TaskManager callbacks, `WorkflowProgressEvent`, AgentRail/output stream and Scheduler messages; Session VCS has a per-session durable WAL with monotonic `LogEntry.event_id`, replay and truncation. Scope/A1/A2 add no Task event envelope. |
| Composition attempted | Session VCS can replay session context/state deltas but is rewindable, not keyed to mandatory TeamTask scope/stream, and not in the TaskDao state/outbox transaction. Callback/progress payload + VCS therefore cannot reconstruct a canonical Task event head without a second owner or crash gap. |
| Classification | `AGENTCORE_PR_CANDIDATE` — event half of `ADD-02` |
| Target owner/API | Extend TaskDao with store-local `TaskEventEnvelope` and `append_event_in_transaction`; expose `read_events(scope, stream_id, after_seq, limit)` and atomic head. |
| JiuwenSwarm Adapter | Map generic state/outcome/progress event payload to P3 status/result/text/voice projection; adapter never writes an alternate event sequence. |
| Test oracle | Existing event identity/order/reopen/multi-task page/atomic replay tests; OJ-G0 event identity/watermark tests; new state-plus-event crash atomicity and cross-scope zero-read conformance. |
| Dependencies | `SCOPE-01`, `EXEC-OWN-01`, `ADD-01`. |
| Retirement Gate | Task mutation and event/outbox are one transaction, restart replay is gap-free, and LiveVoice event table is read-only/quiesced. |
| Confidence/open issue | High. Envelope payload versioning must stay generic and bounded. |

#### EVT-02 — event subscription transport

| Field | Required content |
|---|---|
| Capability ID | `EVT-02` |
| LiveVoice file | `jiuwenswarm/server/live_voice/task_event_subscription.py` |
| LiveVoice symbol | `TaskEventSource`; `TaskEventAuthoritySource`; `TaskEventSubscriptionState/Snapshot`; `TaskEventSubscription.start/_start_authority_atomic_replay/_start_authorized_baseline/next_event/close/snapshot/_poll_loop/_accept_batch` and authorization/close helpers |
| Current responsibility | Establishes authorized baseline, replays to an atomic event head, tails polling batches, applies backpressure and closes safely. |
| Authority/data owned | Runtime subscription/queue state only; durable event truth stays in the source. |
| Product coupling | Async polling cadence and product authorization grant shape are JiuwenSwarm integration choices; ordered stream subscription is generic. |
| Existing AgentCore evidence | No durable event source exists; once `ADD-02` exists, its read/head API can supply a generic stream. |
| Composition attempted | Current base progress/message streams lack atomic baseline plus replay. With `ADD-02`, the remaining logic is transport rather than a second authority. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | Generic AgentCore event reader/subscription over `TaskEventEnvelope`; optional polling helper may live beside TaskDao, with no in-memory truth beyond queue state. |
| JiuwenSwarm Adapter | Supplies mapped scope/auth, polling/cancellation lifecycle and converts envelopes to product projections. |
| Test oracle | Existing start/close/race/auth/replay/batch/backpressure subscription tests against AgentCore event source. |
| Dependencies | `EVT-01`, `SCOPE-01`. |
| Retirement Gate | Subscription reads only the AgentCore sequence/head and all close/race tests pass without persisting a JiuwenSwarm event copy. |
| Confidence/open issue | Medium; whether AgentCore exposes async subscription or only read/head is an API packaging choice. |

#### EVT-03 — durable consumer/channel cursor and unread page

| Field | Required content |
|---|---|
| Capability ID | `EVT-03` |
| LiveVoice file | `jiuwenswarm/server/live_voice/formal_task_models.py`; `jiuwenswarm/server/live_voice/task_store.py`; `jiuwenswarm/server/live_voice/presentation_ledger.py` |
| LiveVoice symbol | `TaskUnreadPage`; `TaskEventConsumerCursorBaseline`; `TaskEventConsumerAuthorityPage`; Store `unread_events_page/consumer_progress_authority_page/ack_events/_ack_history_step`; `next_task_presentation_event`; `TaskPresentationConsumptionOwner.reserve_next/consume` cursor segments |
| Current responsibility | Tracks last consumed sequence per stable consumer/channel, returns unread events against an atomic head, and advances with identity/fingerprint checks. |
| Authority/data owned | Durable consumer/channel cursor and ACK replay result. |
| Product coupling | Consumer/channel labels and presentation class mapping are product-specific; monotonic cursor CAS is generic. |
| Existing AgentCore evidence | `MessageDao.mark_message_read/mark_messages_read` stores timestamp-oriented read state. Base/Scope/A1/A2 have no stream sequence cursor. |
| Composition attempted | Message timestamp watermark + EventEnvelope cannot distinguish consumers/channels, same-time events, or independent text/voice ACK and therefore loses/repeats presentation. |
| Classification | `AGENTCORE_PR_CANDIDATE` — detailed as `ADD-03` |
| Target owner/API | Internal `CursorDao` beside the accepted AgentCore event owner: `(physical session, scope, stream incarnation/legacy baseline, bound principal, opaque consumer, channel) -> sequence/version/forward-receipt head`. It composes the PR 05 verified snapshot/prefix primitive, returns typed read failure, advances by CAS, and verifies a reconstructible immutable forward-receipt chain. Raw DAO/Manager mutation stays internal until PR 09. |
| JiuwenSwarm Adapter | Maps product response/task route and presentation class into an opaque registration request, then translates DOM adoption or voice playout receipt into the bound PR 09 cursor-advance call. It cannot select another physical cursor identity or equate cursor ACK with product closure. |
| Test oracle | Rebuild unread/forward/exact-replay/conflict/same-time/multi-consumer cases plus reverse orphan receipt, whole-state loss policy, incarnation/baseline reuse, normal-clean tombstones/reservation races, scoped replay IDs, typed corruption, bounded receipt growth, current DDL/SessionFileStore zero-change and wrong-principal/channel/scope full zero-effect conformance. Historical Team-cascade and unlimited covered-no-op positives are rejected. |
| Dependencies | `EVT-01`; accepted PR 05 incarnation/baseline/normal-clean semantics; PR 09 for the public bound facade. |
| Retirement Gate | AgentCore cursor is sole durable generic consumption truth; exact replay survives normal clean, no old cursor crosses stream incarnation, and text/voice product receipts remain independently acknowledged through bound adapters only. |
| Confidence/open issue | Medium. Formal replay must freeze registration/full-loss detection, existing-cursor terminal drain after retirement, typed read outcomes and bounded receipt replay/retention without inventing product presentation closure. |

#### EVT-04 — task progress source and generic projection

| Field | Required content |
|---|---|
| Capability ID | `EVT-04` |
| LiveVoice file | `jiuwenswarm/server/live_voice/task_progress_return.py` |
| LiveVoice symbol | `PreparedTaskProgressSource`; `_ConsumerTaskEventSubscription`; `TaskEventAuthorityProgressSource`; source start/next/close/baseline methods; `_project_task_progress_event/project_task_progress_event`; `TaskProgressProjection`; `TaskProgressOriginBinding` |
| Current responsibility | Reads authorized Task events and projects generic Task state/progress into a product-neutral intermediate projection. |
| Authority/data owned | Runtime source position only; projection is derived from canonical events. |
| Product coupling | Origin binding includes product response/generation; the Task state/progress projection itself can be generic. |
| Existing AgentCore evidence | Base `WorkflowProgressEvent` and AgentRail/output events supply progress facts, while `ADD-02` supplies durable Task envelopes. |
| Composition attempted | AgentCore progress payload + EventEnvelope + CursorStore is sufficient for generic projection; response-generation binding must remain downstream. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | AgentCore progress/event envelope schema and reader; generic `TaskProgressProjection` may be a derived SDK value, not stored authority. |
| JiuwenSwarm Adapter | Input: AgentCore event/progress fact plus product origin. Output: JiuwenSwarm text/voice notification intent. |
| Test oracle | Existing projection/order/terminal/handoff/auth tests plus base progress-event compatibility conformance. |
| Dependencies | `EVT-01`, `EVT-02`, `EVT-03`. |
| Retirement Gate | Projection consumes only AgentCore facts and cannot advance the durable cursor until downstream class ACK. |
| Confidence/open issue | Medium; align a minimal generic progress vocabulary without importing spoken policy. |

#### EVT-05 — response PresentationLedger

| Field | Required content |
|---|---|
| Capability ID | `EVT-05` |
| LiveVoice file | `jiuwenswarm/server/live_voice/presentation_ledger.py` |
| LiveVoice symbol | `PresentationSurface`; `HistorySurfacePolicy`; `PresentationState`; `PresentationUnit`; `PresentationAck`; `PresentationRecord`; `PresentedHistorySpan`; `PresentationLedger.begin_response/produce/enqueue/acknowledge/close_surface/invalidate_response/presented_history/snapshot` |
| Current responsibility | Fences response-generation presentation across text and voice surfaces, validates segment alignment, and decides what may enter visible/spoken history. |
| Authority/data owned | Response/surface presentation state and history-adoption proof. |
| Product coupling | ResponseRef, generation, text DOM, voice playout, cross-surface alignment and history policy are Voice/product semantics. |
| Existing AgentCore evidence | No AgentCore task/execution component owns response generation or media presentation, nor should it. |
| Composition attempted | Event cursor can prove Task-event consumption but cannot prove a particular response generation was rendered or spoken. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm Conversation Runtime / `PresentationLedger`. |
| JiuwenSwarm Adapter | Consumes derived Task notification content and, after real DOM/playout acknowledgement, advances the AgentCore consumer/channel cursor. |
| Test oracle | Existing cross-surface alignment, stale generation, ACK identity, invalidation, close, and presented-history tests. |
| Dependencies | `EVT-03` for Task-event presentations; conversation presentation is otherwise independent. |
| Retirement Gate | Not retired. It must not be replaced by a Task cursor. |
| Confidence/open issue | High. |

#### EVT-06 — Task presentation consumption and class ACK

| Field | Required content |
|---|---|
| Capability ID | `EVT-06` |
| LiveVoice file | `jiuwenswarm/server/live_voice/presentation_ledger.py` |
| LiveVoice symbol | `TaskPresentationRuntimeReceipt`; `TaskPresentationDelivery`; `TextPresentationAdoptionAck`; `TaskPresentationConsumptionOwner.reserve_next/mark_text_adopted/mark_voice_presented/consume/close_response/_require_delivery/_require_runtime` |
| Current responsibility | Reserves one Task event for a response/surface, accepts only authentic text adoption or voice playout receipts, and then consumes the event. |
| Authority/data owned | Product runtime receipt and response binding; current implementation also advances LiveVoice durable cursor. |
| Product coupling | DOM adoption, playout receipt, response/generation and surface lifecycle are product semantics. |
| Existing AgentCore evidence | `ADD-03` supplies generic cursor CAS only; AgentCore has no product runtime receipt. |
| Composition attempted | Cursor + PresentationLedger cleanly splits generic consumption from product proof. Moving receipt verification upstream would make AgentCore own UI/media state. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | AgentCore `CursorStore.advance`; JiuwenSwarm `TaskPresentationConsumptionOwner` keeps reservation-to-runtime-receipt verification. |
| JiuwenSwarm Adapter | Input: unread AgentCore event. Output: text/voice delivery; authentic receipt produces exactly one cursor-advance command. |
| Test oracle | Existing reserve/adopt/playout/duplicate/stale/wrong-surface/close tests; new cursor adapter zero-advance for forged or stale receipt. |
| Dependencies | `EVT-03`, `EVT-05`. |
| Retirement Gate | JiuwenSwarm retains no durable cursor column and AgentCore never accepts raw product ACK without verified adapter binding. |
| Confidence/open issue | High. |

#### EVT-07 — speech/foreground progress policy

| Field | Required content |
|---|---|
| Capability ID | `EVT-07` |
| LiveVoice file | `jiuwenswarm/server/live_voice/task_progress_return.py`; `jiuwenswarm/server/live_voice/progress_notification_arbiter.py` |
| LiveVoice symbol | `TaskProgressNotificationIntent`; `TaskProgressTextEvent`; `TaskProgressReturnBridge.activate/close/drain_voice/_run/_consume/_advance_voice_without_projection/_deliver_voice/_emit_voice_intent/_deliver_text`; all `ForegroundFact`, `SpeechPolicy`, notification/speech dispositions, verified baseline/projection tokens, and `ProgressNotificationArbiter.offer/drain/acknowledge` policy/validation state |
| Current responsibility | Chooses whether/when a background Task update may interrupt, be spoken, be rendered as text, be deferred, or be suppressed under foreground/generation/backpressure constraints. |
| Authority/data owned | Runtime notification/presentation policy and pending delivery state; cursor advances only after the selected presentation path. |
| Product coupling | Foreground speech, barge-in safety, response generation, voice availability, text fallback and notification capacity are Voice/product policy. |
| Existing AgentCore evidence | AgentCore can emit progress and own a cursor, but has no Conversation Runtime, speech surface or foreground media authority. |
| Composition attempted | Generic event/progress/cursor supplies inputs, but no composition can decide spoken interruption without product media state. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm `TaskProgressReturnBridge` and `ProgressNotificationArbiter`, consuming AgentCore event/cursor adapters. |
| JiuwenSwarm Adapter | The retained product policy is the downstream consumer; it returns only cursor ACK or no-advance evidence. |
| Test oracle | Existing foreground/speech/defer/backpressure/generation/cursor/terminal notification tests, including no-projection advance. |
| Dependencies | `EVT-03`, `EVT-04`, `EVT-05`. |
| Retirement Gate | Not retired. Remove only duplicated event/cursor storage after adapter cutover. |
| Confidence/open issue | High. |

### 7.4 D2 external effects

#### D2-01 — generic external-effect journal and reconciliation protocol

| Field | Required content |
|---|---|
| Capability ID | `D2-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/durability_effects.py`; `jiuwenswarm/server/live_voice/durability_authority.py`; `jiuwenswarm/server/live_voice/task_store.py` |
| LiveVoice symbol | `EffectObservationKind`; `EffectReconciliationKind`; `EffectSettlementKind`; `ExternalEffectBinding/Intent/Dispatch`; `EffectContinuationAuthorization`; `EffectDispatchReceipt`; `ExternalEffectObservation`; `ExternalEffectSettlement`; `effect_fact_bytes/effect_fact_from_bytes`; `EffectReconciliationDecision`; `decide_effect_reconciliation`; `DurabilityMutationAuthorization` and mint/digest helpers; Store `append_durability_effect_fact/read_durability_effects/claim_durability_mutator/release_durability_mutator` |
| Current responsibility | Gives each external effect stable identity, records intent/dispatch/receipt/observation/settlement as an append-only prefix, and chooses retry/verify/compensate/unknown after crash. |
| Authority/data owned | Effect sequence, mutation lease, verified receipt/observation and final disposition; fact values alone explicitly have no call/mutation authority. |
| Product coupling | Effect kind-specific probe and compensation are product/Tool adapters; identity, phases, lease and reconciliation decision are generic. |
| Existing AgentCore evidence | Workflow `engine.Journal` caches/finalizes completed workflow calls; Session VCS supplies a per-session WAL; Checkpointer stores context; AsyncTool runs/cancels; A2 owns execution. Scope/A1/A2 explicitly omit persistent effect receipt/reconcile. |
| Composition attempted | Workflow Journal + Session VCS + Checkpointer + A1 + A2 cannot distinguish crash-before-call, call-without-receipt, receipt-without-settlement, or ambiguous external outcome. VCS is rewindable session state, not an effect ledger. Workflow `engine/` must remain business-agnostic and cannot import AgentTeams TaskDao/A2 modules, so its call cache cannot be made the Task effect transaction owner. |
| Classification | `AGENTCORE_PR_CANDIDATE` — detailed as `ADD-04` |
| Target owner/API | Keep subordinate `openjiuwen.agent_teams.tools.database.EffectDao` in the shared AgentTeams session/transaction boundary while TaskDao remains sole Task/checkpoint owner. Internal operations are plan, claim, purpose-specific one-use CALL/OBSERVE authorization, result-bound receipt/observation finalization, settlement, verified/redacted read, reconciliation and reaping. Authority-free lifecycle/provenance truth is reconstructible; opaque live token material is internal only, and raw DAO/Manager/tokens stay behind the bound PR 10 facade. The first fact and a PR 07-owned generic effect-intent `TaskEventEnvelope` append atomically through the accepted PR 05 canonical event writer, so the non-effect-table event detects whole-ledger loss without becoming a second effect-state owner. Workflow `engine/` may accept only a business-neutral injected protocol; it may not import TaskDao/A2 or own their rows. |
| JiuwenSwarm Adapter | Supplies a declared adapter/provider namespace plus file/project Tool binding, stable idempotency scope, probe, verification and compensation callback. It receives only the exact purpose-bound call/probe request; it cannot choose a physical AgentCore token or append evidence directly. |
| Test oracle | Rebuild D2 duplicate, prefix/projection corruption including canonical-event/all-effect-rows mismatch, all call/probe crash windows, purpose-confusion, receipt/observation/settlement, retry-round, stable-key namespace, Team-clean tombstone, current DDL/SessionFileStore zero-change and non-Voice adapter conformance. Historical never-called receipt/observation positives are rejected. |
| Dependencies | `SCOPE-01`, `EXEC-OWN-01`, `ADD-02`, `ASYNC-01`; no `TASK-05`/checkpoint implementation dependency. Exact runtime registration, Task incarnation, source event and Team deletion reservation come from the accepted execution/event contracts. |
| Retirement Gate | AgentCore journal is sole generic effect truth; every CALL/OBSERVE/result continuation is purpose-bound and consumed once; corrupt/stale/wrong-purpose inputs have zero provider/journal effects; ambiguity is never silently retried; LiveVoice effect rows are quiesced/imported only in a later migration. |
| Confidence/open issue | Medium. Owner placement is resolved to subordinate `EffectDao`, but formal replay must redesign evidence provenance, prefix/projection reconstruction, stable-key namespace, normal-clean tombstones and the PR 10 public split. Preserving the name “Workflow Journal” is not a valid reason to violate the engine boundary. |

#### D2-02 — project/file Tool effect adapter

| Field | Required content |
|---|---|
| Capability ID | `D2-02` |
| LiveVoice file | `jiuwenswarm/server/live_voice/project_code_executor.py` |
| LiveVoice symbol | `_d2_checkpoint_state/_decode_d2_checkpoint_state`; `_expected_project_state_matches`; `_attempt_patch/_apply_attempt_patch`; `DirectProjectCodeExecutorAdapter._d2_binding_for_item/_mutation_authorization/_append_effect/_fork_recovery_lineage/_resume_d2_recovery/_prepare_d2_project_effect/_settle_d2_project_effect/_append_effect_bound_checkpoint/reconcile_durable_effects` |
| Current responsibility | Binds a generic effect lifecycle to a concrete project tree/patch, probes whether it happened, applies or verifies it, and reports ambiguous/compensated settlement. |
| Authority/data owned | Project filesystem observation and effect-specific evidence; current code also writes the generic effect journal. |
| Product coupling | Git/project fingerprints, patch application, filesystem probe and code-task compensation are JiuwenSwarm-specific. |
| Existing AgentCore evidence | `ADD-04` must own generic phases; no AgentCore module can know project-tree equivalence or safe patch application. |
| Composition attempted | Generic EffectJournal + retained project probe/compensator gives complete separation; moving project logic into AgentCore would create product assumptions. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | AgentCore `EffectJournal` from `ADD-04`; its bound coordinator consumes a purpose-specific call/probe authorization once, invokes the exact declared adapter namespace and alone finalizes the returned receipt/observation. Product code never writes an evidence enum directly. |
| JiuwenSwarm Adapter | Input: a bound call/probe request plus expected project state, without a reusable raw AgentCore token. Output: typed `not_observed/observed/ambiguous` evidence and a separately declared compensation relation. |
| Test oracle | Existing real file/project D2 crash-window, retry-readiness, applied-artifact and mismatch-zero-effect tests; inject crash before call, after call, after receipt and before settlement. |
| Dependencies | `D2-01`, `EXE-06`. |
| Retirement Gate | Adapter has no local effect sequence/lease/settlement columns and a forged/stale token causes zero file/Tool effect. |
| Confidence/open issue | High. Compensation availability differs by Tool and must be declared per binding, not assumed. |

#### D2-03 — authority-free recovery facts and verified prefixes

| Field | Required content |
|---|---|
| Capability ID | `D2-03` |
| LiveVoice file | `jiuwenswarm/server/live_voice/durability_readers.py`; `jiuwenswarm/server/live_voice/durability_recovery_facts.py`; `jiuwenswarm/server/live_voice/durability_effects.py` |
| LiveVoice symbol | `DurabilityReadBinding`; `CheckpointPrefixRow`; `EffectPrefixRow`; `_AuthorityFreePrefix`; `VerifiedCheckpointPrefix`; `VerifiedEffectPrefix`; `verify_checkpoint_prefix/verify_effect_prefix`; `ExecutorRecoveryFacts` and all `*_authority` false methods; `_AuthorityFreeEffectFact` authority-false methods |
| Current responsibility | Parses and verifies bounded, unique, digest-bound recovery evidence while making explicit that evidence cannot itself authorize mutation, launch, compensation or settlement. |
| Authority/data owned | No control authority; immutable verified evidence only. |
| Product coupling | Current scope/profile value types come from LiveVoice; the authority-free rule is generic. |
| Existing AgentCore evidence | Checkpointer/Journal provide source records but no equivalent authority-free verified-prefix value; A2 provides the execution relation that must mint actual authority. |
| Composition attempted | Source record + A2 relation still needs a narrow verification/authorization boundary; otherwise callers can treat stale facts as authority. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | Generic verified fact values live with Checkpointer/EffectJournal readers; only TaskDao/EffectJournal may mint mutation/continuation authorization after validating the A2 token. |
| JiuwenSwarm Adapter | Maps project capability/profile/scope into generic read binding and decodes returned evidence; it cannot mint authority. |
| Test oracle | Existing duplicate/out-of-order/corrupt/prefix-digest/stale-profile/generation tests and explicit `*_authority is False` assertions. |
| Dependencies | `TASK-05`, `D2-01`. |
| Retirement Gate | All recovery paths demonstrate evidence-to-authority separation and no direct executor call is possible from a fact object. |
| Confidence/open issue | Medium; generic value naming/serialization should follow AgentCore conventions. |

### 7.5 Agent Bridge and composition

#### BRIDGE-01 — legacy thread-pool AgentBridgePort

| Field | Required content |
|---|---|
| Capability ID | `BRIDGE-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/agent_bridge.py` |
| LiveVoice symbol | `AgentRequest`; `AgentEvent`; `AgentHandler`; `AgentBridgePort.submit/_invoke/close` |
| Current responsibility | Runs a synchronous handler in a local thread pool and returns Agent events. |
| Authority/data owned | Ephemeral worker/future state only. |
| Product coupling | Request/event values reflect the old LiveVoice bridge. |
| Existing AgentCore evidence | Base Runner/Team Runner and AsyncTool already provide Agent/Tool invocation and asynchronous lifecycle. |
| Composition attempted | Base Runner + adapter event projection subsumes the thread-pool wrapper; retaining it adds no authority or safety. |
| Classification | `DIRECT_AGENTCORE — BASE_EXISTING` |
| Target owner/API | OpenJiuwen Runner/Team Runner invocation API; A1 AsyncTool only when background Tool execution is required. |
| JiuwenSwarm Adapter | Pure request/event conversion, if any old caller remains. |
| Test oracle | Port unique submit/close/error tests to the actual Runner adapter; prove no late event after close/cancel. |
| Dependencies | Base Runner; `ASYNC-01` for background work. |
| Retirement Gate | No production caller imports `AgentBridgePort` and actual Runner integration covers its outcomes. |
| Confidence/open issue | High. |

#### BRIDGE-02 — round dispatch, provenance and real Agent stream

| Field | Required content |
|---|---|
| Capability ID | `BRIDGE-02` |
| LiveVoice file | `jiuwenswarm/server/live_voice/agent_bridge_runtime.py`; `jiuwenswarm/server/live_voice/jiuwenswarm_agent_adapter.py` |
| LiveVoice symbol | `AgentBridgeDispatchReservation`; `AgentRoundRequest.source_provenance/fingerprint`; `AgentRoundAdapter.stream`; `AgentBridgeRuntime.submit/reserve_dispatch/begin_dispatch_commit/commit_dispatch/abort_dispatch/rollback_undelivered_dispatch/_dispatch_loop/_run_request`; `JiuWenSwarmAgentAdapter.stream/_validate_request` |
| Current responsibility | Reserves one committed round, binds source provenance, invokes the real JiuwenSwarm/OpenJiuwen Agent stream, and prevents undelivered/duplicate dispatch. |
| Authority/data owned | Conversation-round admission and provenance; actual execution is in OpenJiuwen Runner. |
| Product coupling | Turn commit, round ID, response generation and delivery rollback belong to Conversation Runtime; Agent stream invocation is generic. |
| Existing AgentCore evidence | Base Runner/Agent stream supplies invocation; base lacks LiveVoice TurnCommit/ResponseRef. A1/A2 concern background Task execution, not foreground conversation round authority. |
| Composition attempted | Conversation reservation -> thin Agent adapter -> base Runner is already the correct composition; replacing round authority with TaskDao would conflate conversation and Task. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | Base Runner/Agent stream is the invocation owner; JiuwenSwarm Conversation Runtime remains admission/provenance owner. |
| JiuwenSwarm Adapter | Input: committed `AgentRoundRequest`. Output: validated Agent events/work progress bound to the same round. It holds no AgentCore Task state. |
| Test oracle | Existing bridge reserve/commit/abort/rollback/close/provenance/late-event tests and real JiuwenSwarm adapter stream tests. |
| Dependencies | None for foreground rounds; background task handoff uses `EXE-05`. |
| Retirement Gate | The adapter calls one OpenJiuwen Runner seam and no duplicate generic worker registry remains. Conversation reservation is not retired. |
| Confidence/open issue | High. |

#### BRIDGE-03 — response completion, delivery and round progress

| Field | Required content |
|---|---|
| Capability ID | `BRIDGE-03` |
| LiveVoice file | `jiuwenswarm/server/live_voice/agent_bridge_runtime.py` |
| LiveVoice symbol | `AgentBridgeCompletionStatus`; `AgentBridgeCompletion/Handle`; `AgentBridgeSubmission`; `AgentEventDelivery`; `WorkProgressDelivery`; `AgentBridgeRuntime.next_delivery/close/snapshot/_put_output`; `project_round_work_progress` |
| Current responsibility | Converts Agent stream events into response-scoped delivery, records round completion and closes the response runtime. |
| Authority/data owned | Response/generation delivery lifecycle and ephemeral queue state. |
| Product coupling | Response generation, foreground work progress and delivery queue are LiveVoice Conversation Runtime semantics. |
| Existing AgentCore evidence | Runner can emit stream/progress facts but cannot decide response-generation delivery or presentation. |
| Composition attempted | Base stream facts are inputs only; AgentCore Task/event authority is unrelated to foreground response completion. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm Conversation Runtime and presentation pipeline. |
| JiuwenSwarm Adapter | Retained consumer of OpenJiuwen stream; no background Task authority. |
| Test oracle | Existing completion, ordering, cancellation, close, progress and generation-fence tests. |
| Dependencies | `BRIDGE-02`, `EVT-05` for presentation. |
| Retirement Gate | Not retired. Generic stream projection may be simplified after Runner adapter stabilization. |
| Confidence/open issue | High. |

#### BRIDGE-04 — formal Agent execution carrier and round harness

| Field | Required content |
|---|---|
| Capability ID | `BRIDGE-04` |
| LiveVoice file | `jiuwenswarm/server/runtime/agent_adapter/formal_live_voice.py`; `jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py`; `jiuwenswarm/server/live_voice/agent_conversation_runtime.py` |
| LiveVoice symbol | `FormalContextEntry`; `FormalContextSnapshot`; `FormalAgentExecution`; `FormalAgentFacade`; harness round admission/stream/close segments; `AgentConversationRuntime.select_formal_context` and committed-round dispatch segment |
| Current responsibility | Freezes the conversation context/provenance passed to the Agent, commits one formal round and adapts Agent chunks back to the response. |
| Authority/data owned | Conversation context, interaction/round/response relation and stream delivery; not background Task execution truth. |
| Product coupling | LiveVoice interaction, context selection, response and generation are Conversation Runtime semantics. |
| Existing AgentCore evidence | Base Agent/Runner accepts execution input and streams results; no AgentCore component should own the product conversation snapshot. |
| Composition attempted | Formal carrier -> Agent facade -> base Runner is sufficient. Replacing the carrier with TeamTask would conflate foreground Agent rounds and background Tasks. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | Base Agent/Runner execution request/stream; JiuwenSwarm retains the formal context carrier and response binding. |
| JiuwenSwarm Adapter | Converts `FormalAgentExecution` to the AgentCore Runner request and validates returned chunks against the same interaction/round. |
| Test oracle | Existing round harness/context/generation/stream/final/cancel tests and real-provider formal carrier integration. |
| Dependencies | `BRIDGE-02`, `BRIDGE-03`. |
| Retirement Gate | Runner handoff is direct through one adapter and no duplicate generic Agent execution state is persisted. |
| Confidence/open issue | High. |

#### COMP-01 — P3 Task composition and Store authority

| Field | Required content |
|---|---|
| Capability ID | `COMP-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/p3_authenticated_composition.py`; `jiuwenswarm/server/live_voice/persistent_task_core.py` |
| LiveVoice symbol | `TaskOutboxDiagnosticFact`; `TaskDurabilityDiagnosticSnapshot`; `create_p3_composition_from_environment` Task Store/Core/executor construction segment; `_DirectP3RuntimeOwner`; `P3AuthenticatedComposition.start/stop/reconcile_once/query/handle` Task operation and diagnostic segments; `StoreProductionTaskAuthorityReader` in `p3_production_intent_composition.py` |
| Current responsibility | Constructs the canonical LiveVoice Task Store/executor/Core, starts recovery, handles authenticated Task reads/mutations, and exposes product status/result/event facts. |
| Authority/data owned | Currently composes the entire duplicate LiveVoice Task/Attempt/Event/Outbox/Effect/Cursor authority. |
| Product coupling | Environment/configuration, route result and product response are JiuwenSwarm; generic store/core/recovery are not. |
| Existing AgentCore evidence | Scope/A1/A2 plus `ADD-01..05`, base Checkpointer and Runner form the target shared authority. |
| Composition attempted | Existing base pieces alone fail the event/outbox/effect/cursor gaps; after minimal additions, keeping `SqliteTaskStore` would be a forbidden peer authority. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | AgentCore `TeamTaskManager`/TaskDao, TeamScheduler/Event reader/CursorStore/EffectJournal, A1 runtime, and the `ADD-05` `ExecutionCheckpointRef` publication boundary over base Checkpointer; composition obtains one configured AgentCore facade. |
| JiuwenSwarm Adapter | Authenticates, maps product scope/command/profile/project executor, and translates AgentCore results to P3 envelopes. |
| Test oracle | Entire persistent-core/P3 authenticated integration suite rerun against facade; startup/restart, wrong-auth/scope zero-effect, real Agent/Tool and event/result/presentation conformance. |
| Dependencies | All generic capabilities through `D2-01` and `EVT-03`. |
| Retirement Gate | Isolated facade passes; quiesced import completes; no same-task dual write; canary passes; Store and direct attempt/effect/cursor writes are disabled before deletion. |
| Confidence/open issue | High. Physical import/rollback design is a later packet and is not performed here. |

#### COMP-02 — authenticated principal, project/session authority and telemetry

| Field | Required content |
|---|---|
| Capability ID | `COMP-02` |
| LiveVoice file | `jiuwenswarm/server/live_voice/p3_authenticated_composition.py`; `jiuwenswarm/server/live_voice/product_authority.py` |
| LiveVoice symbol | `AuthenticatedPrincipal`; authenticators; `ResolvedAuthority`; `ServerSessionProjectAuthorityResolver.resolve/revalidate`; `P3RouteTelemetry` and sink; `ProductAuthorityRequest`; `TrustedAuthorityLookup/Resolver/Candidate`; `AuthorityConfirmationBinding`; `ResolvedProductAuthority`; `AuthorityDecision`; `ProductAuthorityService`; `SpeechAuthorityResolverAdapter`; `P2AuthorityAdapter`; `P3AuthorityAdapter/to_task_grant` |
| Current responsibility | Verifies product principal/session/project/revision, resolves trusted authority, validates destructive confirmation and emits route diagnostics. |
| Authority/data owned | Product access, resource target, confirmation and route evidence; it does not own generic Task state. |
| Product coupling | Entire responsibility depends on JiuwenSwarm account/session/project/Voice route policy. |
| Existing AgentCore evidence | Scope candidate can enforce the resulting team/task key but cannot verify these product identities. |
| Composition attempted | Product authority -> `SCOPE-01` mapping is the correct boundary. Moving upstream would make AgentCore an application authorization service. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm product authority service; output maps to scoped AgentCore request. |
| JiuwenSwarm Adapter | Verified product-to-AgentCore scope/token adapter described by `SCOPE-01`. |
| Test oracle | Existing principal expiry/operation/project revision/scope/confirmation/telemetry tests plus wrong mapping zero-effect conformance. |
| Dependencies | `SCOPE-01` for downstream Task calls. |
| Retirement Gate | Not retired. Its Task-store reads are replaced by the AgentCore facade, but product decisions remain. |
| Confidence/open issue | High. |

#### COMP-03 — committed Task intent and unified input

| Field | Required content |
|---|---|
| Capability ID | `COMP-03` |
| LiveVoice file | `jiuwenswarm/server/live_voice/voice_task_bridge.py`; `jiuwenswarm/server/live_voice/unified_committed_input.py` |
| LiveVoice symbol | `TaskIntentDisposition`; `UnifiedCommittedInputRoute`; `CurrentBackgroundTaskContext`; `ResolvedUnifiedCommittedInput`; `TaskIntentSourceSpan`; `ResolvedTaskIntent`; resolver ports; `BoundedAlphaTaskIntentResolver.resolve/resolve_unified`; `TaskIntent`; `VoiceTaskBridge.resolve/resolve_production/resolve_unified/map`; `UnifiedInputAdmission`; `UnifiedForegroundEffectAdmission`; `SqliteUnifiedCommittedInputJournal.admit/renew/wait_for_completion/read_foreground_effect/admit_foreground_effect/checkpoint_foreground_effect*/claim_foreground_effect_recovery/complete_foreground_effect/complete` |
| Current responsibility | Converts only committed text/voice input into bounded Task intent, resolves target/ambiguity, and makes foreground response effects idempotent/recoverable. |
| Authority/data owned | Committed semantic input, Task target/clarification and foreground response-effect admission; not Task execution truth. |
| Product coupling | Voice turn commitment, spans, one-current-task language, clarification, destructive confirmation and foreground response presentation are product semantics. |
| Existing AgentCore evidence | AgentCore `TeamTaskManager` accepts explicit commands but should not interpret speech/committed conversation or own foreground response effects. |
| Composition attempted | Intent adapter can call AgentCore command ledger after product decision; merging journals would conflate input commitment with Task command/external Tool truth. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm Voice–Task Bridge and unified committed-input journal; accepted explicit Task command is passed to `ADD-01`. |
| JiuwenSwarm Adapter | Output: scoped, explicit AgentCore command ID/fingerprint/precondition. Input on status: derived AgentCore Task facts. |
| Test oracle | Existing commit/replay/ambiguity/confirmation/foreground-effect recovery and wrong-origin tests; zero Task mutation before committed intent. |
| Dependencies | `SCOPE-01`, `ADD-01` for dispatch after resolution. |
| Retirement Gate | Not retired. It must cease only duplicated Task-command storage, if any; committed-input truth remains separate. |
| Confidence/open issue | High. |

#### COMP-04 — product composition registry and root

| Field | Required content |
|---|---|
| Capability ID | `COMP-04` |
| LiveVoice file | `jiuwenswarm/server/live_voice/product_composition_registry.py`; `jiuwenswarm/server/live_voice/product_composition_root.py`; `jiuwenswarm/server/live_voice/product_p3_text_adapter.py`; `jiuwenswarm/server/live_voice/p3_production_intent_composition.py` |
| LiveVoice symbol | `AgentServerProductCompositionRegistry` setup/observability/P2 lifecycle/P3 control-intent/progress-presentation/close segments; pending route/presentation/intent structures; `ProductCompositionRoot`, manifest/registration/lease/activation types; `ProductP3TextAdapter` and cleanup/activation owners; call-local confirmation and production-origin authority; production context/model fingerprints |
| Current responsibility | Activates product routes, owns P2/P3 lifecycles, confirmation and origin continuations, presents progress, and coordinates cleanup. |
| Authority/data owned | Product route/response/generation/presentation/confirmation state. Task query/mutation segments currently call the LiveVoice Task authority. |
| Product coupling | Product manifest, Web/Voice route, P2 media, P3 confirmation, response generation and cleanup are application semantics. |
| Existing AgentCore evidence | AgentCore can replace only the Task/event/result/effect/cursor datasource behind the P3 segments. It does not own product activation or presentation. |
| Composition attempted | Thin AgentCore facade under the existing registry preserves product semantics and avoids a second Task truth; moving the registry upstream has no non-Voice justification. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm product composition; Task-facing calls use the facade from `COMP-01`. |
| JiuwenSwarm Adapter | P3 Task query/control/progress/result adapter; all P2/Voice/presentation/confirmation logic remains native. |
| Test oracle | Existing registry/root/text-adapter/production-intent tests plus end-to-end AgentCore-backed P3 query/control/progress/result/presentation cases. |
| Dependencies | `COMP-01`, `EVT-04`, `EVT-06`. |
| Retirement Gate | Not retired. Remove only direct `SqliteTaskStore` and cursor/event/effect access after facade cutover. |
| Confidence/open issue | High. |

#### COMP-05 — production intent, confirmation, model and route policy

| Field | Required content |
|---|---|
| Capability ID | `COMP-05` |
| LiveVoice file | `jiuwenswarm/server/live_voice/production_task_classifier.py`; `jiuwenswarm/server/live_voice/production_task_intent.py`; `jiuwenswarm/server/live_voice/voice_task_policy.py`; `jiuwenswarm/server/live_voice/p3_confirmation.py`; `jiuwenswarm/server/live_voice/p3_product_confirmation.py`; `jiuwenswarm/server/live_voice/p3_model_resolution.py`; `jiuwenswarm/server/live_voice/product_composition_contract.py` |
| LiveVoice symbol | `ProductionTaskIntentClassifierContext`; `ProductionTaskIntentClassifier.parse_structured/classify_natural`; all authenticated Task fact/read, field extraction, origin, confirmation, proposal/request/resolution and clarification schemas; `BoundedClarificationOwner`; `ProductionMultiTaskResolver`; `FormalTaskPolicyAdapter`; `P3ConfirmationBinding`; `SqliteP3ConfirmationLedger`; `BoundedP3ConfirmationOwner`; `ProductP3ConfirmationForwarder`; `ServerModelCatalogResolver`; product route truth/segment/reason/evidence schemas and manifest builders |
| Current responsibility | Classifies committed language, selects/clarifies a product Task target, enforces committed origin and destructive confirmation, resolves an allowed model, and reports truthful product route capability. |
| Authority/data owned | Product semantic proposal, clarification, one-shot confirmation, model/catalog choice and route evidence; none is canonical Task execution state. |
| Product coupling | Natural-language intent, Voice/text origin, product-visible task set, confirmation UX, configured model catalog and product route truth are JiuwenSwarm semantics. |
| Existing AgentCore evidence | AgentCore accepts explicit scoped commands and Agent configuration but has no authority over JiuwenSwarm conversation commitment, confirmation or product route/model catalog. |
| Composition attempted | Product classifier/policy/confirmation -> explicit scoped `ADD-01` command is sufficient. Moving these owners upstream would let AgentCore authorize unresolved or unconfirmed product intent. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm production intent/policy/confirmation/model/route owners; only the final explicit command crosses the `SCOPE-01`/`ADD-01` adapter. |
| JiuwenSwarm Adapter | Output: confirmed scoped command ID/fingerprint/precondition and selected product executor digest; input: read-only AgentCore Task facts used for target disambiguation. |
| Test oracle | Existing structured/natural classifier, multi-task clarification, origin, confirmation issue/forward/consume/replay, model catalog and product-contract tests; rejected, stale, wrong-origin or unconfirmed input must produce zero Task/Agent/Tool/file effect. |
| Dependencies | `COMP-02`, `COMP-03`, `SCOPE-01`, `ADD-01`. |
| Retirement Gate | Not retired. Task facts come from the AgentCore facade, but no Task mutation may occur before committed origin, resolved target and required one-shot confirmation. |
| Confidence/open issue | High. Product capability vocabulary may evolve independently of AgentCore. |

#### HIST-01 — committed formal history side effect

| Field | Required content |
|---|---|
| Capability ID | `HIST-01` |
| LiveVoice file | `jiuwenswarm/server/live_voice/formal_history_writer.py`; `jiuwenswarm/server/live_voice/agent_conversation_runtime.py` |
| LiveVoice symbol | `SessionFormalHistoryWriter.persist_user/persist_assistant`; `AgentConversationRuntime` history-writer construction and committed-user/TEXT-presentation-ACK invocation segments |
| Current responsibility | Writes only committed user turns and assistant text proven adopted by the TEXT presentation surface into product session history. |
| Authority/data owned | External product conversation-history side effect and its committed/presented eligibility; it owns no Task state/event/result/effect truth. |
| Product coupling | TurnCommit, channel, ResponseRef/generation and TEXT PresentationAck are Conversation Runtime/product semantics. Voice playout alone is deliberately not a text-history adoption proof. |
| Existing AgentCore evidence | Session/VCS can persist context, but it does not decide LiveVoice commit or presentation eligibility and cannot replace `PresentationLedger`. |
| Composition attempted | AgentCore-backed Task progress may produce candidate text, but `EVT-03` cursor advance and product TEXT adoption proof must precede history write. Treating Task event consumption as history authority would admit stale/unpresented content. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm `SessionFormalHistoryWriter`, invoked only by Conversation Runtime after committed user input or authentic TEXT adoption. |
| JiuwenSwarm Adapter | For Task notifications, consumes derived text plus authentic presentation receipt; it never writes or settles the AgentCore Task. |
| Test oracle | Existing formal history/Conversation Runtime commit and presentation tests; rejected/stale/uncommitted input, failed delivery, voice-only/unacknowledged text and wrong generation must produce zero history and zero Task mutation. |
| Dependencies | `COMP-03`, `EVT-05`, `EVT-06` for Task-derived presentations. |
| Retirement Gate | Not retired. History remains a separate product side effect and must never be used as Task, effect, cursor or resume truth. |
| Confidence/open issue | High. |

### 7.6 Integrated Web mapping

#### WEB-01 — legacy LiveVoice Task client/bridge/monitor

| Field | Required content |
|---|---|
| Capability ID | `WEB-01` |
| LiveVoice file | `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskClient.ts`; `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskBridge.ts`; `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskMonitor.ts` |
| LiveVoice symbol | execution-context helpers and `createLiveVoiceTaskGateway`; `LiveVoiceTaskBridge` command parsing/run/recover/status/cancel/replace and snapshot methods; `LiveVoiceTaskMonitor` observation/poll/reconcile/notification methods; all exported task/status/execution-target schemas in these files |
| Current responsibility | Maps Web session/project context to gateway calls, parses Task commands/results, keeps a browser task snapshot and polls/reconciles status. |
| Authority/data owned | Browser-derived cache only by design, but legacy recovery/replace logic mirrors Task mutation state. |
| Product coupling | Browser session/project route, transcript feedback and polling UI are product-specific; Task lifecycle/command replay is generic. |
| Existing AgentCore evidence | Target AgentCore Task/event/result facade supplies canonical command replay and reads; product Web still needs a view adapter. |
| Composition attempted | AgentCore facade + Web projection removes the need for browser mutation recovery as truth. Browser cache alone cannot safely replace the durable command ledger. |
| Classification | `ADAPTER_DOWNSTREAM` |
| Target owner/API | `ADD-01` Task command API, Task read/result API, and `EVT-02/03` event stream/cursor behind the server P3 facade. |
| JiuwenSwarm Adapter | Input: verified session/project and UI command. Output: product Task view, feedback and monitor lifecycle; browser state is discardable. |
| Test oracle | Existing client/bridge/monitor target/provenance/recovery/cancel/replace/poll tests rerun against AgentCore-backed server responses. |
| Dependencies | `COMP-01`, `ADD-01`, `EVT-02`, `EVT-03`. |
| Retirement Gate | Legacy gateway cannot mutate a parallel task route and browser recovery never decides canonical command outcome. |
| Confidence/open issue | High; removal timing depends on the product route switch, not AgentCore schema. |

#### WEB-02 — formal P3 Task experience/control/result

| Field | Required content |
|---|---|
| Capability ID | `WEB-02` |
| LiveVoice file | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalP3TaskExperience.ts`; `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskControlLeaf.ts`; `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskResultRoute.ts` |
| LiveVoice symbol | all formal Task method/operation/display/record/command/snapshot types; parse/list/event/result helpers; `FormalP3TaskExperienceOwner.refresh/select/issue/confirm`; control binding/provenance/transition helpers and `FormalTaskControlLeaf`; result schemas/parser and `ProductFormalTaskResultOwner` |
| Current responsibility | Validates server envelopes, projects canonical Task/event/result facts into UI state, prepares confirmation-bound mutations and holds selection hints. |
| Authority/data owned | UI selection, display phase and pending confirmation only; canonical Task/event/result must remain server-side. |
| Product coupling | Display states, selection storage, UI confirmation and adoption context are Web product semantics. |
| Existing AgentCore evidence | AgentCore target supplies the underlying Task/command/event/result truth, not the Web experience. |
| Composition attempted | Stable P3 facade response mapping keeps the leaf thin. Moving UI selection/display upstream would provide no non-Web value. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm Web formal P3 leaf; reads/mutations terminate at the AgentCore-backed server facade. |
| JiuwenSwarm Adapter | These files are the retained view adapter. Inputs are scoped canonical records; outputs are browser snapshots/actions. |
| Test oracle | Existing formal experience/control/result parsing, provenance, transition, selection, confirmation, retry and close tests. |
| Dependencies | `COMP-01`, `EVT-01`, `ADD-01`. |
| Retirement Gate | Not retired. Remove only any assumptions tied to old LiveVoice Store schema after response-contract migration. |
| Confidence/open issue | High. |

#### WEB-03 — formal intent/target recovery and product P2/P3 activation

| Field | Required content |
|---|---|
| Capability ID | `WEB-03` |
| LiveVoice file | `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/formalTaskIntentRoute.ts`; `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP3TaskTargetJournal.ts`; `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts` |
| LiveVoice symbol | `ProductFormalTaskIntentOwner`, recovery journal/checkpoint and intent parsing; target journal persist/inspect/read; `ProductWebP2ActivationOwner`; durable P2 operation journal/replay; `ProductWebP3MutationOwner`; `ProductWebP3ProgressOwner`; route method constants and close/retry/replay helpers |
| Current responsibility | Preserves product intent/target/confirmation across transport ambiguity, owns media/progress activation and retries product operations. |
| Authority/data owned | Browser product-operation checkpoint, target selection, confirmation, media and progress route lifecycle; not generic Task execution. |
| Product coupling | Voice/text source, clarification, confirmation, browser storage, media, barge-in, response generation and route cleanup are entirely product-specific. |
| Existing AgentCore evidence | Command ledger can make the final explicit Task command idempotent; it cannot own pre-command intent or browser/media activation. |
| Composition attempted | Product journal -> explicit AgentCore command cleanly separates intent recovery from Task replay. Treating both as one ledger would authorize an unresolved intent. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm Web/product activation and intent owners; final command calls `ADD-01` through P3 facade. |
| JiuwenSwarm Adapter | Retained product adapter, with canonical Task binding/result returned from the server. |
| Test oracle | Existing intent recovery/claim, ambiguity/confirmation, target journal, P2 durable operation, P3 mutation/progress activation and bounded close retry tests. |
| Dependencies | `COMP-03`, `COMP-04`, `ADD-01`, `EVT-06`. |
| Retirement Gate | Not retired. Ensure browser journal cannot fabricate Task acceptance; only an AgentCore replay record can. |
| Confidence/open issue | High. |

#### WEB-04 — product task presentation/activity projection

| Field | Required content |
|---|---|
| Capability ID | `WEB-04` |
| LiveVoice file | `jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskAdapter.ts`; `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productCompositionContract.ts` |
| LiveVoice symbol | all task activity/monitor/context/transcript/safety/terminal/feedback projection functions; product composition contract constants/types, `createProductCompositionManifest`, and `routeFactFromIntegratedShell` |
| Current responsibility | Derives UI/transcript/speech actions and truthful route diagnostics from Task/product snapshots. |
| Authority/data owned | Derived product presentation and route-evidence snapshot only. |
| Product coupling | Transcript routing, capture resumption, terminal speech, demo disclosure, product segment and fallback truth are JiuwenSwarm/Web/Voice semantics. |
| Existing AgentCore evidence | AgentCore event/result facts provide inputs but cannot decide UI transcript or product route truth. |
| Composition attempted | Pure downstream derivation is already the correct pattern and should remain outside AgentCore. |
| Classification | `LIVEVOICE_KEEP` |
| Target owner/API | JiuwenSwarm Web/product adapters. |
| JiuwenSwarm Adapter | Pure projection from AgentCore-backed P3 envelopes and product route evidence. |
| Test oracle | Existing adapter and product composition contract tests, including safety disclosure and terminal-announcement gates. |
| Dependencies | `WEB-02`, `COMP-04`, `EVT-05`. |
| Retirement Gate | Not retired; ensure projections never persist canonical Task/Event/Result state. |
| Confidence/open issue | High. |

## 8. Four classification lists

### 8.1 Direct AgentCore reuse

| Substatus | LiveVoice responsibility to retire or redirect | Exact AgentCore target |
|---|---|---|
| `BASE_EXISTING` | legacy `AgentBridgePort` and generic Agent/Tool invocation | Agent/Team Runner, `create_deep_agent`, NativeHarness; Workflow/Agent storage remains only a checkpoint foundation |

Only the base Runner/Agent invocation contract is direct reuse today. The local
Scope/A1/A2/ADD/facade implementations are classified separately as AgentCore
PR candidates below; none is an installed capability claim.

### 8.2 Adapter-downstream list

| Capability | AgentCore side | JiuwenSwarm side; why it is not second truth |
|---|---|---|
| Executor profile | A2 owns canonical profile digest/generation at admission | Project/D0-D2 selector maps configuration to one immutable profile; it cannot settle execution. |
| Product scope | Scope TaskDao enforces team/task | Product authority verifies principal/project/session and emits one immutable scope key; it cannot mutate Task state. |
| Agent/Tool handoff | Runner/AsyncTool performs invocation under execution token | Project/session/model resolver and stream codec select the product Agent; they return observations only. |
| Result/adjustment | AgentCore TaskDao owns command replay, outcome and immutable result reference | Project adapter extracts chat/patch artifacts and translates adjustment policy; no result ledger. |
| D1 checkpoint | Checkpointer stores opaque bytes; `ADD-05` lets TaskDao publish the only resume-authoritative execution reference | Project codec/profile binding translates checkpoint data; facts cannot mint resume authority. |
| Event subscription/progress | AgentCore event reader supplies ordered envelopes and generic progress | JiuwenSwarm binds response/generation and derives text/voice notification intent. |
| Presentation cursor | AgentCore CursorStore owns sequence per consumer/channel | JiuwenSwarm verifies DOM adoption or voice playout before issuing one cursor CAS. |
| D2 Tool effect | AgentCore EffectJournal owns identity, lease, phases and settlement | Project/file Tool adapter operates through a bound purpose-specific call/probe request; it never receives a reusable raw token or writes evidence directly. |
| P3/Web task facade | AgentCore owns Task/Attempt/Command/Event/Result/Effect/Cursor | P3/Web maps authentication, product envelopes, view state and confirmation; all browser caches are discardable. |

### 8.3 AgentCore PR candidates

All entries in this section exist only as local candidates and require replay,
review, upstream acceptance and installation before LiveVoice can consume them.
The first group repairs or exposes existing AgentCore owners:

| Candidate | Generic owner and public outcome | Why it is not direct reuse |
|---|---|---|
| `SCOPE_CANDIDATE` | mandatory `(team_name, task_id)` predicates in `TaskDao` / `TeamTaskManager` | the locked/base dependency permits unscoped access; the local correction is not installed |
| `A1_CANDIDATE` | monotonic `AsyncToolRuntime` cancel/wait/terminal callback and reused-ID fencing | the required lifecycle semantics exist only in the local candidate |
| `A2_CANDIDATE` | canonical Task/execution relation, admission, claim, reconcile and token-fenced settlement | the locked/base Task owner lacks this durable execution contract |
| bound Task/checkpoint facade candidate | `TeamAgent.task_authority` returning lifecycle-bound reader/command/cursor/checkpoint sub-authorities over the accepted internal owners | The historical monolithic handle is string-bound and construction-bypassable, while Manager/DAO/raw checkpoint finalization is not an acceptable public product API; PR 09 must rebuild an opaque lease, capability matrix, redacted views and same-ID rebind/in-flight revocation fencing |
| bound effect facade candidate | `TeamAgent.effect_authority` returning `TeamExecutionEffectAuthority` | the least-privilege continuation handle is local only and intentionally excludes reaper/provider policy |

The remaining candidates add generic non-Voice capabilities to the smallest
existing owners. Each addition satisfies all five admission tests below.
“Composition failure” is an authority/crash-safety failure, not a naming
mismatch.

| ID and minimum owner | Locked/base absence | Checked composition remains insufficient | Scope/A1/A2 absence | Non-Voice value | Minimum schema/API and failing oracle; exclusions |
|---|---|---|---|---|---|
| `ADD-01` — extend existing TaskDao/`TeamTaskManager` execution owner with command, terminal outcome and result | AgentTeams `TeamTaskManager`/TaskDao has no durable command fingerprint/replay ledger or immutable token-fenced Task result. Base core controller already has broad `TaskStatus` vocabulary and mutable `Task.outputs/error_message/metadata`, serialized as `TaskManagerState` through Session. | Controller Task/Session restore is a different mutable owner with no TeamTask scope/execution token/command fingerprint, and its save is not the TaskDao transaction. Workflow Journal and Checkpointer likewise cannot atomically replay Task mutation/result. A1 only fences callbacks. | A2 owns execution admission and completed/cancelled settlement but no command ledger, broader outcome/result settlement or immutable result | Any long-running Agent/Tool Task needs idempotent controls and restart-stable outcome/result | Reconcile/reuse existing public status names where semantically equal; add `TaskCommandRecord`, scoped fingerprint/replay/CAS, opaque immutable `TaskResultRef`, and token-fenced settlement in the TaskDao transaction. Oracle: same-ID replay/conflict, stale-token zero effects, restart-stable immutable result. Exclude project artifact schema, UI display and Voice confirmation. |
| `ADD-02` — extend TaskDao and TeamScheduler with EventEnvelope plus transactional dispatch outbox | Base Session VCS already has per-session WAL/replay and monotonic `LogEntry.event_id`; callbacks/progress/Scheduler messages also exist. None is a TaskDao-scoped immutable event plus state/dispatch transaction. | VCS is session-scoped, rewindable/truncatable and not atomic with TaskDao; TaskDao state then Scheduler send loses work, while send then state update can launch unauthorized work. Logs and Workflow Journal do not close either crash window. | Scope adds predicates; A1 worker safety; A2 atomic Task/attempt CAS. None stores Task EventEnvelope/outbox claim/receipt/order. | Any background Agent/Tool Task needs auditable replay and crash-safe dispatch | `TaskEventEnvelope`; `TaskDispatchRecord`; TaskDao state/event/dispatch atomic append; Scheduler claim/complete/release/reclaim. Oracle: crash windows, ordered replay, wrong-token zero launch, multi-team isolation. Exclude JiuwenSwarm transport, spoken policy and project priority policy. |
| `ADD-03` — small CursorStore beside AgentCore event owner | `MessageDao` timestamp watermark is not a per-stream sequence cursor | Timestamp + events cannot isolate consumers/channels or order equal-time events; it cannot express text ACK separately from voice ACK. | No candidate adds cursor/ACK. | Any UI, webhook, audit reader or notification channel needs independent replay position | Internal `CursorDao` composes the accepted event verifier and binds physical session, scope, stream incarnation/baseline, principal, opaque consumer and channel to a CAS position plus reconstructible immutable forward-receipt chain/head. Normal clean preserves tombstones; replay identity is cursor-scoped; typed corruption/full-loss and bounded receipt policy are frozen before replay; PR 09 alone exposes the bound public facade. Oracle: exact replay/reverse orphan, same-ID recreation, normal-clean reservation races, same-time, duplicate, bounds and wrong-principal/channel/scope full zero effects. Exclude DOM/playout receipt semantics, product closure and response generation. |
| `ADD-04` — subordinate EffectJournal in the AgentTeams database boundary, linked to A2 execution | Checkpointer and business-neutral Workflow Journal store context/completed-call prefixes; Session VCS stores rewindable session deltas. None stores external-effect intent/dispatch/receipt/observation/ambiguous settlement. | Workflow `engine/` is forbidden from importing AgentTeams business modules; Session VCS is not an effect ledger; neither shares the A2 Task transaction. Adding AsyncTool still cannot distinguish crash-before-call from call-without-receipt or decide safe retry/compensation. | A1/A2 explicitly exclude persistent effect receipt/reconcile. | Any Agent Tool touching files, APIs, money, messages or external systems needs safe ambiguity handling | Keep subordinate `EffectDao` in the AgentTeams session/database and A2 execution boundary. Add reconstructible authority-free lifecycle/provenance truth while keeping opaque live tokens internal; atomically pair genesis with a PR 07-owned generic effect-intent `TaskEventEnvelope` appended through the accepted PR 05 canonical event writer as a whole-ledger-loss anchor; bind runtime/phase/incarnation/provider identity; add purpose-specific one-use CALL/OBSERVE plus result finalization, per-dispatch evidence, stable-key conflict, reservation-aware normal-clean tombstones and a PR 10 bound public facade. Oracle: every call/probe crash window, wrong-purpose/never-called evidence zero effects, corrupt or wholly missing journal/projection zero authority, current DDL/SessionFileStore zero change, duplicate/stale generation/round, retry evidence isolation and ambiguous no-retry. Exclude project/file probe, compensation selection and product confirmation. |
| `ADD-05` — execution-checkpoint publication in the A2 TaskDao owner | Base Checkpointer/Agent/Team/Workflow storage can save/recover opaque context; core controller Session persistence and VCS can restore state. None publishes a token/version-fenced checkpoint reference as canonical TeamTask resume authority. | Checkpointer payload + A2 relation without a publication link leaves crash ambiguity and lets callers mistake orphan/stale payload for authority; Session/controller restore is a different owner. | A2 stores profile/generation/owner/version but no checkpoint reference/publication API. Scope/A1 add none. | Any restartable non-Voice Agent/Task needs to bind resume data to the exact admitted execution. | Add an immutable checkpoint reference/head plus exact source event under runtime/phase/incarnation authority. Publication must be preauthorized once, derive a scoped storage key server-side, perform payload `put`, then atomically consume the token into reference/event/head truth; initially invalid callers have zero store effect and only post-authorization orphans are durable/reapable. Reuse an accepted `ADD-04` continuation or keep the reservation checkpoint-only—never create a second general effect ledger. Oracle: crash before/after preauthorization/payload/finalize, stale/corrupt/mismatched source/reference zero `put` or launch, normal-clean tombstone replay. Exclude project checkpoint codec, automatic restore and product retention policy. |

No addition creates a new top-level `DurableTaskAuthority`: `ADD-01`, `ADD-02`
and `ADD-05` extend the A2 TaskDao/`TeamTaskManager`/TeamScheduler boundary;
`ADD-03` is subordinate to the event owner. `ADD-04` must use AgentTeams
business storage tied to the A2 relation; it must not turn business-neutral
Workflow `engine/` or Session VCS into a parallel Task/effect authority.

### 8.4 LiveVoice/JiuwenSwarm retained list

| Retained owner | Concrete product semantics that prevent AgentCore ownership |
|---|---|
| Conversation Runtime, formal round carrier and response bridge | interaction/turn/response/generation, committed round, context selection, foreground Agent response and stream delivery |
| Voice–Task Bridge and unified committed-input journal | committed Voice/text input, source span, intent/target/ambiguity, one-current-task language, destructive confirmation and foreground response-effect idempotency |
| Product authority | verified principal/project/session/revision, trusted candidate, confirmation, product route authorization and telemetry |
| Production intent/confirmation/model/route owners | natural/structured intent classification, multi-task clarification, committed origin, one-shot destructive confirmation, product model catalog and truthful route capability |
| Project code executor resource adapter | project root/model/session Agent binding, Git worktree, patch/artifacts, unsafe-link policy, file/project probe/compensation and resource cleanup |
| PresentationLedger and Task presentation adapter | text DOM adoption, voice playout, response/surface generation fence, history policy and cross-surface alignment |
| SessionFormalHistoryWriter | committed user turn and authentically TEXT-adopted assistant history; rejected, stale, voice-only or unacknowledged text must not be persisted |
| TaskProgressReturnBridge and ProgressNotificationArbiter | foreground/speech/barge-in safety, defer/suppress/fallback policy and presentation backpressure |
| Product composition registry/root and P2/P3 adapters | product segment activation, route truth, media lifecycle, confirmation continuation, progress cleanup and observability |
| Web formal experience/intent/result/activation owners | browser selection/display, transcript/capture behaviour, intent recovery, product operation retry, media/progress activation and safety disclosure |

## 9. Double-authority and retirement Gates

| Current writable truth | Target sole writable truth | JiuwenSwarm data allowed after cutover | Forbidden migration state |
|---|---|---|---|
| `SqliteTaskStore` task/attempt/admission | Scope+A2 TaskDao/`TeamTaskManager` plus `ADD-01` | product scope mapping and derived P3 view | same command or attempt written to both stores |
| LiveVoice commands/business decisions/results | `ADD-01` TaskDao transaction | product confirmation, opaque artifact payload/reference target | browser/adapter result treated as canonical or replayed independently |
| LiveVoice events/outbox/reconciliation | `ADD-02` TaskDao/TeamScheduler | product event projection and transport observation | Task state committed without event/dispatch, or dispatch before token admission |
| `_DirectProjectAttemptJournal` execution/lease/terminal | A2 execution relation + A1 runtime | worktree/patch/cleanup evidence only | local journal can revive, cancel or terminalize an AgentCore execution |
| LiveVoice checkpoint/effect tables | `ADD-05` TaskDao checkpoint publication plus `ADD-04` business-storage EffectJournal | project checkpoint codec and Tool probe/compensation evidence | fact object or adapter mints mutation/call authority, or Workflow engine/Session VCS becomes a peer business authority |
| LiveVoice task-event consumption | `ADD-03` CursorStore | response reservation and authentic DOM/playout receipt | text and voice ACK share an accidental cursor or adapter stores a second cursor |
| session/history stores | unchanged product conversation history | committed user turns and authentically TEXT-adopted assistant spans | session history used as Task/execution/event/effect truth, or rejected/stale/voice-only/unacknowledged text writes history |

Required cutover sequence for each authority is: isolated read/write facade on
candidate data; conformance; quiesce old writers; deterministic import and
verification; switch all callers; canary; keep old data read-only for rollback;
only then physically remove duplicate schemas/wrappers. No shadow or dual write
is allowed, even temporarily, for the same scoped entity.

## 10. Test and evidence Gates

For every later implementation packet, [`TESTING.md`](../../TESTING.md) assigns
the risk per changed boundary. Scope, task/execution ownership, checkpoint,
outbox/event, effect and cursor cutovers are Tier 3. At minimum:

- positive business scenarios must complete through a real Agent/Tool where the
  boundary launches one;
- negative wrong-scope/profile/generation/owner/command/ACK/effect inputs must
  fail closed;
- forbidden Task/Event/Result/Tool/file/presentation/history side effects must be
  asserted as zero, not inferred from an exception;
- boundary/race/restart/idempotency/forensic evidence must cover accepted
  cancellation, competing terminal outcomes, crash windows, duplicate delivery,
  stale continuation and ambiguous external effects;
- committed/confirmed intent and TEXT presentation adoption must gate product
  history: rejected, stale, voice-only or unacknowledged text has zero Task and
  zero history write;
- independent semantic/security review is required for each Tier 3 authority
  change; count-only or coverage-only evidence cannot close it.

Existing reusable oracles are the G0 and G1-A conformance tests plus LiveVoice
`test_task_core.py`, `test_persistent_task_core.py`,
`test_project_code_executor.py`, D2 durability tests,
`test_task_event_subscription.py`, presentation/progress tests,
`test_agent_bridge_runtime.py`, formal executor integration, product composition
and Web formal-route suites. A candidate XPASS is evidence only after its target
public seam is the one production callers use.

## 11. Coverage inventory

This inventory closes the first five requested groups. Utility serializers,
validators and private helpers inherit the classification of the authority-bearing
symbol that exclusively calls them; helpers shared across responsibility segments
are explicitly split in the records above.

| Requested group | Production paths/symbol families classified | Records |
|---|---|---|
| Executor/runtime | `executor_port.py`; `executor_capabilities.py`; `project_code_executor.py` port, profile, direct journal, live worker, cancel/wait, result/adjustment, Agent launch, worktree/cleanup and restart segments | `EXE-01..06`, `ASYNC-01` |
| Task core/authority | `formal_task_models.py`; `task_core.py`; `persistent_task_core.py`; `task_store.py` Task/Attempt/admission/command/result/outbox/recovery/scope plus storage-engine/schema/migration methods | `SCOPE-01`, `EXEC-OWN-01`, `TASK-01..05`, `STORE-01`, `EVT-01`, `EVT-03`, `D2-01` |
| Event/result/presentation | `task_event_subscription.py`; `presentation_ledger.py`; `task_progress_return.py`; `progress_notification_arbiter.py`; Event/Result/Cursor Store methods | `EVT-01..07`, `TASK-03` |
| D2 | all effect/authority/prefix/recovery fact schemas and Store methods; direct executor project effect plan/dispatch/receipt/probe/reconcile/crash paths | `D2-01..03`, `EXE-06` |
| Agent Bridge/composition/Web | legacy and runtime bridge, formal carrier/harness, real Agent adapter, P3 authenticated/product composition, production classifier/intent/policy/confirmation/model/route contract, committed formal history, Task Web client/bridge/monitor/formal owners | `BRIDGE-01..04`, `COMP-01..05`, `HIST-01`, `WEB-01..04` |

## 12. Historical open questions

The 2026-08-25 update in section 0 resolves the local candidate design questions
below. They remain here to preserve why each composition was investigated.
Physical migration and upstream acceptance remain open.

1. Which stable public facade exposes A2 prepare/start/claim/settle without
   encouraging direct DAO calls? TaskDao remains the storage owner regardless.
2. This migration uses A2's existing opaque digest. Whether a future
   cross-provider execution profile deserves a separate generic schema remains
   open; JiuwenSwarm D0/D1/D2/project policy must not leak into it.
3. Which base controller `TaskStatus` names are semantically reusable for A2
   failed/interrupted/unknown outcomes, which need an execution-specific value,
   and which immutable result-reference fields are truly generic?
4. Which durable transport boundary does TeamScheduler claim, and what exact
   receipt distinguishes accepted delivery from unknown delivery after restart?
5. What narrow TaskDao/Checkpointer link gives checkpoint monotonicity without
   turning Checkpointer into Task authority or requiring a cross-store atomicity
   claim it cannot provide?
6. Does CursorStore retain a close/tombstone fact per consumer/channel, or only a
   monotonic sequence/version? Response closure remains a product fact.
7. EffectJournal methods stay on a subordinate EffectDao sharing TaskDao's
   session/transaction/identity boundary. Formal replay must still freeze the
   purpose-specific continuation/result protocol, adapter/provider namespace,
   prefix/projection reconstruction and PR 10 public split. Business-neutral
   Workflow `engine/` may receive an injected protocol but may not import
   TaskDao/A2; each Tool declares probe/compensation availability.
8. A1 deliberately has no cancellation-timeout/escalation policy. Product
   shutdown may report retained cleanup, but must not falsely settle quiescence.
   The integration must also replace A2 `Team.cancel_member`'s current
   reset-before-runtime-cancel ordering with fence -> A1 cancel/wait -> A2
   settlement, or re-scope a protocol that proves equivalent zero effects.
9. The physical import, rollback window, canary population and old-schema removal
   are a later migration packet. This review proposes authority boundaries but
   does not perform or approve that migration.

## 13. Recommended local PR-preparation and later migration order

1. `OJ-G1-SCOPE`: replay/review the Scope candidate and run wrong-team
   positive/negative/zero-effect conformance against its public seams.
2. `OJ-G1-A1`: replay/review the AsyncTool lifecycle candidate; prove
   hostile cancellation, reused-ID isolation and no spill/injection after cancel.
3. `OJ-G1-A2`: replay/review the execution-ownership candidate. Real product
   launch/control wiring is a later LiveVoice adapter packet.
4. `OJ-G1-TASK-RESULT`: replay/review the local `ADD-01` candidate; verify command,
   terminal outcome and immutable-result conformance.
5. `OJ-G1-EVENT-DISPATCH`: replay/review the local `ADD-02` candidate and prove
   transactional event/outbox plus scheduler crash windows.
6. `OJ-G1-D2`: preflight/replay the subordinate-EffectDao `ADD-04` candidate
   without coupling Workflow `engine/` to TaskDao; settle whether its accepted
   one-use continuation is also the checkpoint payload-write primitive. Use
   generic and non-Voice crash-window evidence; project/file adapters remain
   downstream.
7. `OJ-G1-D1`: replay/review `ADD-05` from the accepted payload-effect topology,
   or from a deliberately checkpoint-only reservation if reuse is rejected.
   Prove initially invalid requests have zero payload-store effects and that
   post-authorization orphan/stale data grants zero resume authority.
8. `OJ-G1-CURSOR`: replay/review `ADD-03`; product text/voice presentation ACK
   adapters are later LiveVoice work.
9. `OJ-G1-FACADE`: replay/review the bound Task/checkpoint/effect public seams.
   Building the isolated JiuwenSwarm adapter is a later feature-branch packet.
10. `OJ-G1-CUTOVER` (later, separately authorized): design and rehearse quiesced
   import, verification, rollback and canary; only after acceptance retire
   `SqliteTaskStore` generic tables, `_DirectProjectAttemptJournal` execution
   truth and duplicate wrappers.

These packets are dependency order, not a priority or readiness change. This
mapping itself performs none of them.

## 14. Documentation authority

This map refines symbol ownership under the current OJ-G1-A status; it does not
change capability completion, product readiness, or queue priority in
[`STATUS.md`](../STATUS.md). Stable authority boundaries remain those in
[`FULL_SOLUTION_2026-07-30.md`](../architecture/FULL_SOLUTION_2026-07-30.md),
especially Conversation Runtime, Task Control Core, Executor and Voice–Task
Bridge separation. This review provides the newer factual inventory and a
proposed refinement of the older audit's coarse reuse classification; it does
not supersede an accepted architecture decision. The G0/G1-A packets remain
test evidence, not production-credit claims.

No LOC count, LOC estimate, reduction percentage, or size-based priority is part
of this review. No production code, test, dependency lock, database, AgentCore
candidate worktree, or remote reference is changed by this document.
