# AgentCore PR 06: execution-checkpoint publication implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Publish an opaque checkpoint reference as the resume-authoritative
head for one exact TeamTask execution without moving product payload policy
into AgentCore.

**Architecture:** TaskDao first performs immutable identity replay/conflict
lookup. For a fresh identity it validates the exact current runtime/phase and
reserves one checkpoint publication with a one-use authorization and a server-
derived scoped storage key. ExecutionCheckpointCoordinator writes opaque bytes
through an injected payload store only after that authorization, then TaskDao
consumes the same token while atomically storing checkpoint metadata and its
canonical source event. Only a post-authorization failure may leave an explicit,
reapable payload orphan; an initially invalid caller never reaches the payload
store and a receipt never grants Task authority.

**Risk and dependency:** Tier 3 durability/recovery authority. Depends on PR 03
execution tokens and PR 05 canonical events. The review-only source diff is
473ad7cf..7c08730f on codex/ac-pr06-checkpoint.

## Owned surfaces

- Candidate generic export surface: openjiuwen/agent_teams/checkpoint.py and
  openjiuwen/agent_teams/__init__.py. The final export set remains a scope
  decision; raw DAO/Manager authority is never public and PR 09 owns the bound
  facade.
- Schema/storage/runtime: schema/task.py, tools/models.py,
  tools/database/engine.py, tools/database/task_dao.py and
  tools/task_manager.py.
- PR 05 launch-registration truth, normal Team retirement and the later PR 09
  bound-public facade are affected dependency boundaries; PR 06 must not invent
  weaker parallel authority for them.
- Primary test:
  tests/unit_tests/agent_teams/test_execution_checkpoint_publication.py.
- Historical candidate docs are F_86/S_28; allocate fresh names at replay
  (tentatively F_104/S_31) and update the final PR 05 event feature.

## Contract

- ExecutionCheckpointAuthority publishes and reads metadata for an exact Team,
  Task, execution ID and execution token.
- ExecutionCheckpointPayloadStore put/get owns opaque bytes and returns a
  bounded receipt; it grants no execution or mutation authority.
- ExecutionCheckpointCoordinator.publish first performs immutable exact-replay/
  conflict lookup. A committed exact replay returns its existing authority-free
  record without calling payload `put`; only a fresh publication obtains a
  one-use authorization, writes under its server-derived scoped key and
  finalizes that exact token. load_current verifies metadata, its exact source
  event and payload digest/size before reading bytes.
- Exact replay remains idempotent after terminal/reset/ordinary clean. A fresh
  stale owner, wrong Team/session, corrupt source event or conflicting head
  fails closed.
- Initially invalid scope/owner/version/round/incarnation/Team-reservation
  requests never call payload `put`; post-authorization orphans are durable,
  bounded and reapable but never current execution authority.
- Checkpoint codecs, Jiuwen project files, compatibility and product payload
  retention policy remain downstream. PR 06 still owns bounded protocol-level
  retention and reaping for post-authorization payload orphans.
- checkpoint.py and checkpoint-test quality fixes from fbfb4c5f belong here.

## Replay and verification

1. Rebase after PR 03/05 and record dependency SHAs.
2. Restore test_execution_checkpoint_publication.py from 30897cd0 plus its
   fbfb4c5f corrections; run without implementation and record red:

       uv run pytest tests/unit_tests/agent_teams/test_execution_checkpoint_publication.py -q

3. From the exact accepted PR 05 tip, implement only the accepted checkpoint
   delta using current public-export and migration conventions; treat
   `5e4355ec` and the owned `fbfb4c5f` hunks as historical evidence, not commits
   to replay.
4. Rerun the primary file, emphasizing concurrent head publication, restart,
   stale owner, corrupt reference/event and payload-orphan cases.
5. Run supported-dialect DDL compilation, changed-file Ruff/format, isolated
   Mypy for checkpoint.py, compileall and git diff --check.
6. Obtain Tier-3 review focused on reference/payload ordering, replay truth,
   source-event verification and accidental authority minting.

## Replay preflight — 2026-08-25

Formal replay is blocked on the exact packaged and reviewed PR 05 tip. The
historical source/test/docs commits are `5e4355ec`, `30897cd0` and `7c08730f`;
their range is read-only evidence and must not be layered onto the PR 03
technical worktree. PR 05 still has open launch, event, incarnation and
SessionFileStore decisions, so no reproducible PR 06 dependency base exists.

The historical implementation cannot be replayed mechanically. Reimplementation
must:

- extend the final PR 03–05 execution, event, Team-reservation, Task-incarnation
  and DDL contracts. Historical reset/settle/delete tests bypass current owned
  runtime quiescence and historical engine/model bodies restore ordinary
  cascades and migration behaviour already rejected by the dependency packets;
- require the exact PR 05 proof that the execution runtime is registered under
  cancellation/quiescence authority before accepting a fresh checkpoint. The
  historical positive test deliberately publishes before dispatch receipt and
  its docs say transport acceptance is irrelevant. That is incompatible with
  PR 05's late-launch finding: a pre-launch logical `owned` row must not mint a
  resume-authoritative checkpoint. The final gate must follow the selected PR 05
  model, whether ownership begins only after registered acceptance or a separate
  durable runtime-start fact is required;
- bind publication to every generic lifecycle fact needed to reject a stale
  producer. Execution ID/version, profile/generation and owner epoch are
  necessary but may be insufficient when a Task incarnation or review/subphase
  can change without advancing execution version. The replay must either bind a
  monotonic Task/incarnation revision and the relevant phase token, or explicitly
  constrain checkpoint publication to a phase where the existing execution CAS
  is complete. It must not let an old-round callback advance the resume head of
  a later round;
- preserve checkpoint references as session-domain tombstones beside execution,
  command, event and dispatch history. The historical checkpoint has both Team
  and attempt/Task cascades and its test expects ordinary Task deletion to erase
  the reference. Under the accepted dependency direction, ordinary Task/Team
  clean must leave immutable checkpoint/reference/source-event facts available
  for exact audit/replay; only explicit session-domain destruction removes them;
- perform immutable checkpoint-ID replay/conflict lookup before requiring a
  current unreserved Team, so exact read-only replay remains stable after
  terminal/reset/ordinary clean. Fresh publication must then take the shared
  reservation-aware Team mutation lock and revalidate the complete current
  execution/runtime/phase/head binding;
- verify the checkpoint row's exact canonical source event on every public or
  authority-bearing read/replay: Team/stream, event ID/sequence/type,
  execution ID/version and bounded payload/reference digest must agree. The
  historical row digest excludes source-event identity and historical reads do
  not join the event, despite this packet's corrupt-source fail-closed contract.
  Either implement that verification in PR 06 or keep the seam internal until
  PR 09 owns the verified public projection;
- replace the historical payload-first trust boundary. Before `put`, TaskDao
  must validate exact session/Team/Task/incarnation/execution/runtime/phase/head
  authority under the reservation-aware Team lock and persist a one-use
  publication authorization carrying a server-derived scoped storage key. The
  payload receipt is then finalized only by consuming that exact token in the
  reference/event/head transaction. Initially invalid or already reserved
  callers must never call the store. Only a crash/cancellation/commit failure
  after valid preauthorization may orphan bytes, and that orphan must have a
  durable state, bounded quota/retention and a named reaper. A best-effort read
  check or caller-chosen key earns no authority or atomicity credit;
- settle the overlap with PR 07 rather than creating a second general external-
  effect ledger. Replay must either order PR 07 first and reuse its accepted
  one-use continuation/settlement protocol for payload `put`, or deliberately
  define a checkpoint-only reservation that cannot authorize arbitrary provider
  effects and is later mapped to the generic journal. This dependency decision
  is part of PR 06 scope freeze;
- reject caller-chosen shared-store identity. Historical storage is unique only
  per physical session/Team while the public Port receives an unscoped caller-
  chosen checkpoint ID. The final storage key must be derived from the durable
  one-use preauthorization and bind a stable session/Team/Task-incarnation/
  execution/checkpoint namespace; callers may supply opaque checkpoint identity
  input but never the physical shared-store key;
- justify fixed payload, locator and identity limits as generic AgentCore safety
  policy or make them adapter capabilities. They must not be inherited from a
  LiveVoice payload size and must not silently make otherwise valid Agent/Tool
  state unpublishable;
- keep `LoadedExecutionCheckpoint` and every immutable record authority-free.
  `load_current` reads DB truth before a potentially slow external `get`; a
  concurrent reset/settlement can stale that snapshot before bytes return. The
  API and tests must require a later exact reauthorization before restore/launch
  side effects and must not call the returned bytes current execution authority;
- decide the root-export boundary with PR 09. The generic payload Port,
  coordinator and value objects may be reusable public types, but raw
  TaskDao/TeamTaskManager publication authority must remain module-internal and
  session-bound authority belongs to PR 09. Root exports cannot expose an
  unbound capability or claim verified public checkpoint reads before source
  validation exists; and
- preserve current `DbSessions.write()` DDL locking, candidate-table snapshots,
  watchdog/retry behaviour and deletion-reservation migration. Checkpoint tables
  must drop before attempt tables only during explicit session cleanup; supported
  dialect compilation does not replace real row-lock service evidence.

Before restoring the historical red suite, four policy choices must be frozen:

1. runtime registration proof and which durable state makes fresh publication
   legal;
2. the monotonic Task-incarnation/phase binding for a resume head;
3. whether PR 06 reuses the accepted PR 07 one-use external-effect protocol or
   owns a strictly checkpoint-only reservation, including its server-derived
   key, post-authorization orphan state, quota/retention and reaper; and
4. external checkpoint-ID namespace plus which checkpoint types are public in
   PR 06 versus deferred to the bound PR 09 facade.

Tier-3 red/green evidence must rebuild, rather than copy, the historical cases
and add:

- a real registered/quiesceable runtime publishing its first checkpoint only
  after the selected PR 05 launch proof, followed by cancellation that silences
  the same execution; pre-registration, permanently rejected and late-launch
  paths produce no checkpoint head/reference/event and never call payload
  `put`;
- an old review/subphase and an old Task incarnation racing a later phase or
  rebuilt Task, proving the stale callback cannot advance head, append an event,
  publish a reference or authorize restore;
- two independent `DbSessions` competing for the next head, the same exact
  checkpoint ID, and different IDs at the same sequence. One reference/event/head
  wins, exact concurrent replay is stable, and every losing external payload is
  classified under the selected orphan policy;
- initially invalid scope/owner/version/review round/Task incarnation and an
  already reserved Team proving payload `put` is never called; shared-store
  cross-session/Team/execution collisions must be impossible because the key is
  server-derived and scoped;
- preauthorization followed by payload `put` while reset, settlement, review-
  round advance, normal clean and Team reservation race in both orders; plus
  `put` success followed by event/reference/commit failure, cancellation before
  and after `put`, and lost commit ACK, proving DB rollback, one-use token
  consumption, cancellation propagation and durable/reapable orphan accounting;
- malformed receipt, wrong Team/task/execution/profile/generation/owner/version,
  stale head and cross-Team external checkpoint-ID collision, with explicit
  zero assertions for AgentCore rows/events/authority, payload `put` and
  SessionFileStore mutation on every initially invalid path;
- source event missing or changed by type, stream, ID, sequence, execution token,
  payload digest or reference digest, proving exact/history/current/load APIs all
  fail closed before payload `get` at the selected public boundary;
- ordinary Task delete and normal Team clean followed by exact replay/history
  read and same-ID rebuild under the PR 05 incarnation policy, while current
  resume returns none and explicit session destruction removes checkpoint,
  attempt, command, event and dispatch tombstones together;
- `load_current` paused in external `get` while reconcile/reset/terminal/clean
  wins, proving returned data grants no restore/launch side effect without a
  fresh exact authorization;
- current owned cancellation/reset/terminal/reconcile races through the PR 03
  quiescence and recovery seams, not the historical direct public calls; and
- current write-locked SQLite migration/reopen/drop, supported-dialect DDL and
  Team reservation races, with real PostgreSQL/MySQL lock behaviour left an
  explicit non-claim when services are absent; and
- a root-export lock proving no raw TaskDao, TeamTaskManager, publication manager
  or other unbound mutation authority is public; if verified checkpoint reads
  remain deferred to PR 09, PR 06 must not export a facade that implies them.

Historical closure counts and its prior review do not transfer to this replay.
The independent preflight review reports **4 Critical / 2 Important** against
the historical candidate: preauthorization/store ordering, tombstone identity,
runtime/phase/incarnation binding and source-event verification are Critical;
the root public boundary and obsolete DDL/helper replay are Important. These are
replay requirements above, not findings accepted into a formal branch.
Formal PR 06 branch readiness is **No** until PR 05 is packaged and every policy
choice above is accepted.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): publish authoritative execution checkpoints”.

The PR body must explain opaque payload separation, exact execution binding,
replay/restart/corruption evidence and why only post-authorization, bounded,
reapable and authority-free payload orphans can exist. Exclude product codecs,
project-file policy, product payload-retention policy, migration of LiveVoice
state and automatic resume orchestration; do not exclude PR 06's protocol-level
orphan quota, retention or reaper.
