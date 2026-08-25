# AgentCore PR 05: canonical Task events and dispatch implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Commit canonical Task events and execution-launch dispatch truth in
the same transactions as their owning Task mutations.

**Architecture:** An append-only TeamTask event stream provides ordered Task
facts. A durable dispatch row tracks claim, authorization, delivery resolution
and reconciliation for launch delivery; the scheduler drains it without
minting its own Task authority.

**Risk and dependency:** Tier 3 transaction, delivery and mutation authority.
Depends on PR 03 and PR 04. The review-only source diff is
55b13458..473ad7cf on codex/ac-pr05-event-dispatch.

## Owned surfaces

- Schema/storage: openjiuwen/agent_teams/schema/task.py,
  tools/models.py, tools/database/engine.py and tools/database/task_dao.py.
- Normal Team retirement becomes an affected boundary in tools/database/team_dao.py
  and its clean/runtime callers if the package retains the claim that every
  canonical Task deletion is recorded before ordinary Team clean.
- Runtime: tools/task_manager.py and agent/scheduling/scheduler.py.
- Primary test:
  tests/unit_tests/agent_teams/test_task_event_dispatch.py.
- Affected test:
  tests/unit_tests/agent_teams/test_task_command_result.py.
- Historical candidate docs are F_85/S_27; allocate fresh names at replay
  (tentatively F_103/S_30) and update the final PR 04 feature only where the
  transaction boundary changes.

## Contract

- TaskEventEnvelope/TaskEventPage expose canonical, contiguous, scoped Task
  facts through get_task_event_head and read_task_events.
- TaskDispatchRecord/TaskDispatchOpResult support get, claim, authorize,
  complete, release, reject, mark-reconcile, reconcile and expired-claim reap.
- Task mutation, emitted event and required launch dispatch commit or roll back
  together.
- An expired/foreign/stale dispatch token has zero launch or ledger effects;
  ambiguous delivery cannot be retried as known-not-sent.
- Product response, voice, Web, DOM and playout events are excluded.
- The fbfb4c5f event-dispatch test hunks are folded here. Its sole
  command-result formatting hunk belongs only to PR 04.

## Replay and verification

1. Rebase after PR 03/04 and record dependency SHAs.
2. Restore test_task_event_dispatch.py from f401d2a4 and run it with the
   dependent command-result suite before implementation; record red:

       uv run pytest tests/unit_tests/agent_teams/test_task_event_dispatch.py tests/unit_tests/agent_teams/test_task_command_result.py -q

3. Starting from the exact accepted PR 04 tip, implement only the PR 05 contract
   on the current transaction helpers. Use 78b4a36c as evidence, never as a
   replacement function body, and fold only its event-dispatch fbfb4c5f
   corrections.
4. Rerun both files, repeat dispatch claimant/expiry/precommit-failure races,
   and verify every current Task writer emits the selected canonical event.
5. Run supported-dialect DDL compilation, file-backed SQLite reopen and
   rollback cases, changed-file Ruff, compileall and git diff --check.
6. Obtain Tier-3 review focused on atomicity, contiguous sequence allocation,
   dispatch ambiguity, authorization consumption and forbidden launch effects.

## Replay preflight — 2026-08-25

Formal replay remains blocked on reviewable PR 03 and PR 04 dependency tips.
The historical source/test/docs commits are `78b4a36c`, `f401d2a4` and
`473ad7cf`; `fbfb4c5f` contributes only the already-assigned focused cleanup.
They remain read-only evidence. PR 05 must not be layered into the dirty PR 03
worktree or presented as implemented while PR 04 contract decisions and issue
metadata are still unresolved.

The historical implementation cannot be replayed mechanically. Reimplementation
must:

- extend the accepted PR 03/04 transaction helpers, execution quiescence,
  review-round CAS, five-state terminal set, Team deletion reservation and
  current `DbSessions.write()` migration/watchdog design. The historical engine
  and termination helpers predate those contracts and must not replace them;
- keep Task event, dispatch, command and execution identities as session-domain
  tombstones across ordinary Task deletion and normal Team clean. Historical
  event and dispatch models have a Team cascade that would erase the immutable
  stream and delivery history; ordinary Team deletion must not own that cascade.
  Explicit session-domain destruction remains the operation that may remove the
  dynamic tables;
- replace the accidental deleted-Task identity policy with an explicit one.
  The historical candidate rejects same-ID recreation only because the new
  sequence-one event collides with the preserved stream. PR 04 preparation,
  however, includes same-ID rebuild cases. Before implementation, PR 05 must
  either (a) deliberately retire `(session, team, task)` forever until explicit
  session destruction and re-scope the PR 04 rebuild contract, or (b) support a
  new incarnation using a durable stream head/incarnation fence so sequence and
  late-callback authority remain safe. This is a shared protocol decision and
  must be re-scoped/re-tiered before code; database uniqueness remains only a
  backstop, never the policy definition;
- serialize every Task/event/dispatch writer against
  `Team.deletion_reservation_id`, not only claim, reset, reconcile, graph mutation
  and explicit Task deletion. This includes create, command, preparation,
  admission, all current PR 03/04 terminal and review writers, legacy
  compatibility writers, dispatch settlement/reconciliation where mutation is
  still legal, and any repair sweep that changes Task truth. Exact immutable
  replay after retirement may remain read-only; no new write may enter a retired
  or reserved Team domain;
- close the ordinary Team-clean writer gap. Historical PR 05 writes a
  `DELETED` event for `TaskDao.delete_task`, but normal Team deletion cascades
  current Tasks without a per-Task terminal fact. To retain the advertised
  complete canonical stream, normal clean must append a bounded retirement or
  deletion event for every current Task before the Team row is removed, under
  the same reservation and transaction authority. Its private retirement seam
  must present the exact reservation token; ordinary writers continue to reject
  every reserved Team. Force/session-domain destruction may deliberately erase
  the whole stream. If that atomic contract cannot be implemented in this
  packet, the package must be re-scoped and must stop claiming complete writer
  coverage;
- define legacy migration baseline semantics. Adding `event_head = 0` to an
  existing Task does not reconstruct its prior history. The replay must either
  append an explicit bounded bootstrap fact before its first post-upgrade
  change, or expose partial-history/baseline metadata in the page contract and
  require consumers to read a current Task snapshot before tailing. Prose alone
  is not a machine-consumable distinction, and the package must not imply that
  pre-upgrade history can be replayed;
- preserve the existing Task and SessionFileStore input contract. Canonical
  event payloads must not include raw Task content or product/media/file data,
  and a new payload bound must not silently narrow a previously accepted title
  or content mutation. Use bounded facts/digests or first establish a compatible
  shared bound. Malformed, stale, conflict, replay, no-op and rollback paths must
  leave Task rows, event heads, dispatch rows and authoritative session-file
  bytes unchanged;
- close the existing SessionFileStore transaction gap before claiming complete
  event atomicity. Current create/graph spill and content update can change a
  task-id file before the SQL transaction and cannot be rolled back when event
  append, dispatch flush or final CAS fails. The replay needs an accepted
  immutable staged-reference/commit protocol, an equally safe rollback design,
  or an explicit scope reduction that excludes those writers from the atomic
  claim. PR 04's possible title-only command fallback does not solve legacy
  create, update or graph mutation;
- inventory every current Task, execution, dependency and review writer after
  PR 03/04 instead of restoring the historical fixture list. In particular,
  owned cancellation remains reachable only through the runtime-quiescence seam,
  old review callbacks retain exact-round fencing, and all five terminal
  outcomes produce the accepted dependency/event projection without reopening
  generic active-state mutation. `cancel_all_tasks` must also preserve PR 03's
  all-or-nothing rollback when any selected execution cannot be settled;
- keep event and dispatch reads scoped to the physical session plus exact Team
  and Task/dispatch identity, including preserved Task/Team tombstones. These
  are module-level/internal callable seams until the bound facade packet; PR 05
  does not create a package public API, consumer ACK or cursor authority; and
- preserve supported-dialect DDL, file-backed SQLite reopen behaviour, current
  dynamic-table creation/drop ordering and Team reservation migration. Only the
  PR 05 event/dispatch schema may be added to the accepted dependency design.

Three dispatch decisions must be frozen before the red suite is restored:

1. A permanently `REJECTED` launch currently closes only the dispatch row and
   leaves the admitted execution `owned`. The package must define an atomic,
   generic recovery truth: for example, move the exact attempt to a non-running
   recoverable disposition, or require and implement a durable explicit recovery
   transition. Product retry/failure policy remains excluded, but a known
   rejected launch cannot be advertised as end-to-end truthful while it leaves
   an unmarked apparently running owner indefinitely.
2. Successful authorization currently leaves no durable authorization fact;
   every expired `claimed` row is therefore treated conservatively as an unknown
   delivery. The replay must either persist a compare-and-set authorization
   transition so never-authorized expiry can be distinguished from send-capable
   ambiguity, or explicitly accept/test that all claim expiry requires manual
   reconciliation and grant no stronger authorization-consumption credit.
3. `ACCEPTED` must have a precise generic meaning. If it means only that an
   external queue accepted the request, marking dispatch complete removes the
   token-staling fence before a cancellable runtime is registered, so Task
   settlement can win and the external work can launch late. Completion may be
   recorded only when the receipt proves the exact runtime is registered under
   PR 03 cancellation/quiescence authority, or the dispatch must remain in a
   fenced state until that proof exists.

In addition to rebuilding the historical matrix on the accepted dependency
tips, Tier-3 red/green evidence must cover:

- explicit Task delete followed by same-ID recreation, and normal Team clean
  followed by same Team/Task IDs, under both sides of the selected identity
  policy: either deterministic refusal with zero changes, or a new incarnation
  with contiguous stream order and zero authority from late old callbacks;
- normal Team clean emitting the selected retirement fact for every current
  legacy and native Task, preserving event/dispatch history, while explicit
  session destruction removes the dynamic domain;
- Team reservation racing every writer class, admission, claim/authorization,
  dispatch reconciliation and repair sweep, with the loser producing zero Task,
  dependency, review, attempt, event, dispatch, file or launch effects;
- migrated `event_head = 0` Tasks under the selected bootstrap/baseline policy,
  including first mutation, deletion, restart and bounded page reads;
- complete current writer inventory, all five terminal outcomes, downstream
  unblocking and review-round races, proving exact replay/no-op/rejection emits
  zero duplicate events and successful multi-row mutations remain atomic;
- two independent `DbSessions`/connections paused between event-head allocation
  and append, proving concurrent winners receive unique contiguous sequences and
  a rolled-back allocation leaves no permanent gap;
- page-head snapshot racing a concurrent append, proving one page returns only
  events at or below its observed head and later pages contain no gap or
  duplicate;
- oversized or non-JSON event facts and existing maximum-sized accepted Task
  inputs, proving validation happens before head or file mutation and does not
  narrow the established Task contract;
- admission/event/dispatch rollback, two claimants, stale/wrong-Team tokens,
  authorize-vs-settle, terminal-before-claim, receipt replay/conflict, known
  not-sent backoff, permanent rejection, callback exception and unknown delivery;
- cancellation immediately before/after authorization and during delivery,
  including failure or repeated cancellation while recording ambiguity, proving
  either a durable reconciliation marker or an expiry path that cannot blind
  redeliver. Scheduler `CancelledError` must still propagate to its caller after
  the durable state is marked or left safely reapable;
- accepted receipt racing Task cancellation/settlement, proving the exact
  runtime is already registered and quiesceable before the dispatch fence is
  removed; and
- permanent rejection crossed with execution recovery, normal Team clean and
  late callbacks, proving no false running owner, unauthorized retry, Task
  mutation or external launch;
- normal clean and restart crossed with every dispatch state (`pending`,
  `claimed`, `reconcile_required`, `completed`, `rejected`), proving unresolved
  external authority blocks clean while stable ledger history survives it;
- wrong-Team get/claim/authorize/complete/release/reject/mark/reconcile/reap
  using colliding identities, with zero foreign Task, attempt, event, dispatch
  and delivery effects;
- `NOT_SENT` release racing a terminal writer in both lock orders, proving the
  winner leaves no stale claim authorization, blind retry, duplicate event or
  forbidden launch; and
- `cancel_all_tasks` with a late CAS loss for one candidate, proving the whole
  Task/attempt/dependency/event batch rolls back without gaps.

Historical tests are evidence, not accepted fixtures. Their direct reset/cancel
of owned executions, generic active-state mutations, incomplete Team-clean
coverage and accidental sequence-collision oracle must be replaced with tests
that exercise the accepted PR 03/04 authority rather than loosening it.

Independent Tier-3 read-only review reports that the historical candidate has
four critical design conflicts and five important replay conflicts against the
current dependency contracts. Formal PR 05 branch readiness is **No**: it may be
created only from the exact packaged and reviewed PR 04 tip after real-issue
metadata, three-commit history and the decisions above are closed.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): add canonical Task events and transactional dispatch”.

The PR body must explain atomic Task/event/dispatch publication, delivery-token
fencing and recovery evidence. Exclude consumer cursors, response/presentation
receipts, product launch selection, LiveVoice policy and external effects.
