# AgentCore PR 08: Task-event consumer cursor implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Let a scoped generic consumer read and atomically acknowledge the
canonical TeamTask event stream with exact replay and corruption fencing.

**Architecture:** CursorDao is the internal subordinate cursor owner beside the
accepted PR 05 event stream. It reuses PR 05's verified stream/head/prefix
primitive rather than implementing a second EventEnvelope validator. Cursor
identity binds the exact session/Team/stream incarnation or migration baseline,
consumer and channel; raw read/advance seams stay internal until PR 09 exposes a
principal-bound public facade. Product delivery remains downstream.

**Risk and dependency:** Tier 3 durable consumer authority. Depends on PR 05
canonical events and their selected Task-incarnation/legacy-baseline/normal-clean
contract, but not on checkpoint or external-effect semantics. PR 09 owns the
public construction path. The review-only source diff is
8f30c02c..2cc81078 on codex/ac-pr08-event-cursor.

## Owned surfaces

- Schema/storage: openjiuwen/agent_teams/schema/task.py,
  tools/models.py, tools/database/cursor_dao.py,
  tools/database/__init__.py and tools/database/engine.py.
- Internal runtime seam: tools/task_manager.py. Root/package exports and the
  public principal-bound construction path are deferred to PR 09; PR 08 must
  not make raw consumer/channel mutation authority public.
- Accepted PR 05 event reader/verifier, Team deletion reservation and explicit
  session cleanup are affected dependency seams, not duplicate PR 08 owners.
- Primary test:
  tests/unit_tests/agent_teams/test_task_event_cursor.py.
- Historical candidate docs are F_88/S_30; allocate fresh names at replay
  (tentatively F_106/S_33).

## Contract

- Authority-free cursor/page/result values bind exact physical session, Team,
  stream incarnation or declared migration baseline, consumer and channel.
- CursorDao reuses the accepted PR 05 canonical reader/verifier in the same SQL
  snapshot/transaction. Read returns a typed absent/retired/corrupt/success
  result; corruption must not collapse into the same `None` as no stream.
- Advance uses an ID scoped to the full logical cursor plus exact request facts,
  not one caller-contended Team-global namespace. Exact accepted replay is
  checked identity-first; changed facts conflict and never advance another
  consumer/channel.
- Stale target, changed replay facts, wrong principal/scope/incarnation/
  baseline, event gaps/digest drift or corrupt cursor/receipt/provenance fail
  closed with zero cursor, Task, event, file or product effects. Fresh
  registration rejects a reserved or retired Team; fresh forward mutation is
  reservation-fenced and follows the later-frozen existing-cursor terminal-drain
  policy after retirement. Identity-first immutable exact replay survives
  normal clean.
- Separate consumers/channels never share authority.
- Ordinary Task deletion and normal Team clean preserve cursor/receipt history
  as session-domain tombstones. Explicit session-domain destruction is the only
  removal path; no historical Team cascade may silently reset consumption.
- DOM adoption, response generation, playout and voice delivery ACK remain
  LiveVoice-owned product receipts.

## Replay and verification

1. Rebase on accepted PR 05; record its SHA.
2. Rebuild test_task_event_cursor.py from the accepted PR 05/08 contracts,
   using `15bd4cbc` only as historical evidence. Do not restore the
   Team-cascade, Team-global advance-ID, raw public Manager or covered-no-op
   receipt oracles. Run the rebuilt file before implementation and record red:

       uv run pytest tests/unit_tests/agent_teams/test_task_event_cursor.py -q

3. From the exact accepted PR 05 tip, implement only the accepted cursor delta.
   Treat `73301660` as historical evidence, not a commit to replay, and preserve
   current upstream model/migration/SessionFileStore conventions.
4. Rerun the full primary file and repeat same/different-target concurrency,
   append-after-read, corruption and commit-failure cases.
5. Run supported-dialect DDL compilation, file-backed SQLite reopen/isolation,
   changed-file Ruff, compileall and git diff --check.
6. Obtain Tier-3 review focused on prefix verification, replay binding,
   cursor/receipt physical corruption and accidental product-ACK semantics.

## Replay preflight — 2026-08-25

Formal replay is blocked on the accepted PR 05 stream identity, baseline and
normal-clean contract plus the PR 08 decisions below. Historical source, test
and docs commits are `73301660`, `15bd4cbc` and `2cc81078`; their range is
read-only evidence and must not be layered onto a formal dependency branch.

The historical implementation cannot be replayed mechanically. Reimplementation
must:

- keep `CursorDao` and any token/receipt-bearing Manager helpers internal until
  PR 09. Historical `TeamTaskManager.read_task_event_unread` and
  `advance_task_event_cursor` accept caller-selected consumer/channel values,
  while `TeamDatabase` documentation invites direct DAO use. That lets one
  holder read or advance another consumer's durable position. PR 09 must bind
  the exact session/Team/member or application principal plus opaque
  consumer/channel capability; authority-free values may not confer mutation;
- bind cursor and receipt identity to the accepted PR 05 stream incarnation and
  legacy baseline, not merely `(team_name, task_id)`. Task same-ID recreation,
  migrated `event_head = 0` streams and normal-clean Team-name reuse must never
  reinterpret an old position or receipt as authority over a new stream;
- compose the accepted PR 05 event snapshot/head/prefix verifier under the same
  `DbSessions` transaction. Historical `cursor_dao.py` duplicates payload,
  envelope, head, terminal and prefix validation in roughly a second event
  reader; it can drift from PR 05 and cannot claim integrity stronger than the
  accepted canonical stream. Shared internals remain business-neutral and do
  not create a second event owner;
- preserve cursor positions, accepted advance receipts and event history as
  session-domain tombstones across ordinary Task deletion and normal Team
  clean. Historical foreign keys cascade on Team deletion, its positive test
  requires that data loss, and `_lock_team` ignores deletion reservation. Exact
  receipt replay/conflict lookup must be identity-first; every fresh cursor
  mutation must use the accepted reservation/retirement lock. Explicit session
  destruction alone removes the dynamic domain;
- scope an advance ID to the complete logical cursor/principal identity.
  Historical `(team_name, advance_id)` uniqueness lets one stream/channel
  reserve a durable conflict for every other consumer in the Team. Exact replay
  remains permanent within its own scope, and raw collation-sensitive identities
  are still checked against portable physical keys/guards;
- make cursor projection and forward-advance provenance mutually verifiable
  without scanning unbounded history. Historical read checks only receipt key/
  guard counts when no cursor exists and ignores corrupt/orphan receipts once a
  cursor exists. Deleting the receipt that established the current version lets
  the original `advance_id` be recreated through the covered-ACK path as a new
  non-advancing result. Make the cursor a reconstructible projection anchored
  by a unique immutable forward-receipt chain/head, so missing/corrupt current
  or predecessor provenance fails read, forward advance and replay while exact
  historical replay still returns the original result;
- replace `None` conflation with typed fail-closed outcomes. Historical read
  converts invalid input, absent stream, retired scope, corrupt event/cursor and
  database-value errors into the same `None`, so a caller cannot distinguish
  “nothing unread” from “consumption truth is unsafe” and may silently close a
  poll loop;
- reject or explicitly bound new already-covered/no-op receipts. Historical
  callers can mint an unlimited immutable receipt for the same old event by
  changing `advance_id`, without moving the cursor. Freeze the retained replay
  horizon/count/size policy for forward receipts and prove over-limit requests
  have zero writes; product retention remains downstream only where it does not
  weaken generic replay/conflict truth;
- freeze how a logical cursor is registered and retired. Deleting both the
  cursor and all its receipts currently looks identical to a never-created
  `0/0` cursor and can replay already-consumed events. Either add a durable
  registration/presence/close anchor outside the mutable cursor projection, or
  explicitly narrow the full-loss claim and require a separately tested
  downstream dedupe contract. Normal Team retirement must also decide whether
  an already-registered cursor may drain through the terminal event; no option
  may infer DOM, speech, response or presentation closure; and
- preserve current `DbSessions.write()` serialization/watchdog/retry behaviour,
  write-locked dynamic DDL, Team reservation migration, current
  SessionFileStore hydration and child-before-parent explicit cleanup. The
  historical 46/435/aggregate counts and prior review do not transfer, and
  dialect compilation is not real PostgreSQL/MySQL locking/collation evidence.

Before rebuilding the red suite, freeze:

1. exact stream-incarnation/legacy-baseline identity inherited from PR 05;
2. principal-bound consumer/channel construction in PR 09 and which PR 08
   schema/result values remain internal versus authority-free public data;
3. scoped advance-ID identity, exact-replay horizon and receipt/projection
   integrity shape;
4. typed read failure states and the stable unread-page snapshot contract;
5. registration/full-loss/close semantics without product presentation policy;
6. normal-clean read/drain/fresh-advance rules plus identity-first replay and
   explicit session destruction; and
7. shared PR 05 event verification and current upstream DDL/SessionFileStore
   integration surfaces.

Tier-3 red/green evidence must rebuild, rather than copy, the historical cases
and add:

- one bound non-Voice consumer opening/reading an accepted PR 05 stream,
  advancing a forward contiguous prefix, replaying the exact accepted ID after
  restart and reading the next page, without product receipt or raw authority;
- wrong physical session, Team, Task incarnation/baseline, bound principal,
  consumer, channel, stream, head, cursor sequence/version, event ID/digest,
  page facts and advance ID across read/replay/fresh advance, with zero cursor,
  receipt, Task, event, SessionFileStore and downstream effects;
- two principals/consumers/channels using the same textual advance ID without
  conflict, while same full-scope ID exact replay succeeds and changed facts
  conflict; case/accent-sensitive identities remain exact on every dialect;
- same-ID Task/Team recreation and migrated legacy baseline cases under the
  accepted PR 05 policy, proving no old cursor/receipt authority crosses the
  incarnation boundary;
- missing/corrupt/reordered PR 05 head, event, prefix and baseline followed by
  unread and advance through the shared verifier, proving PR 08 neither accepts
  nor repairs an alternate event truth;
- missing/corrupt cursor projection, receipt head/chain/key/guard/fingerprint/
  result and bound event, including cursor-only, receipt-only and complete
  consumer-state loss under the selected registration policy;
- forward, covered, duplicate, delayed and over-retention advance attempts,
  maximum page/identity/payload/integer/version bounds and receipt-growth limits;
- read snapshot racing event append, Task delete and normal Team clean; fresh
  advance and exact replay racing deletion reservation in both lock orders;
- ordinary Task deletion and normal Team clean followed by read, exact replay,
  same-ID rebuild and terminal drain under the selected policy. Only explicit
  session destruction removes event/cursor/receipt tombstones;
- two independent `DbSessions` racing same/different forward targets, same/
  changed replay facts, registration and retirement, plus commit-failure and
  ACK-commit-before-caller-return recovery;
- current `test_database.py`, `test_database_concurrency.py`,
  `test_db_sessions_watchdog.py`, `test_task_event_dispatch.py`,
  `test_task_manager.py` and `team_workspace/test_session_file_store.py`
  regressions, with rejected/rolled-back paths byte-comparing SessionFileStore;
  and
- supported-dialect DDL/identity compilation with real PostgreSQL/MySQL
  transaction, row-lock and collation behaviour left an explicit non-claim when
  services are unavailable.

The independent preflight review reports **2 Critical / 4 Important** against
the historical candidate. These findings are replay requirements above, not
findings accepted into a formal branch. Historical closure counts and review do
not transfer. Formal PR 08 branch readiness is **No**.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): add scoped Task-event consumer cursors”.

The PR body must explain cursor identity, unread/advance CAS, exact replay and
corruption/concurrency evidence. Exclude response reservation, browser/DOM
adoption, audio playout, presentation recovery and consumer-specific product
policy.
