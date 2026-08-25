# AgentCore PR 07: external-effect journal implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development while replaying this plan, then use
> superpowers:requesting-code-review before declaring the local package ready.

**Goal:** Provide generic durable truth for external-effect intent, dispatch,
receipt, observation, settlement and reconciliation under one exact Task
execution.

**Architecture:** EffectDao is the subordinate effect owner and stores an
append-only, digest-linked fact prefix plus a deterministically reconstructible
authority-free lifecycle projection. Opaque live claim/continuation material
remains internal and is represented in facts only by non-secret authorization
identity, purpose, version and consumption state. Purpose-typed CALL and OBSERVE continuations are consumed
once under the complete current execution/prefix/Team-reservation binding before
an exact adapter boundary is crossed; only result-bound finalization may append
receipt or observation evidence. TaskDao remains sole Task/execution/checkpoint
owner and blocks token-staling Task writes while an effect is unresolved. Raw
DAO/Manager/token surfaces remain internal until PR 10 owns the bound public
facade.

**Risk and dependency:** Tier 3 external side-effect and durability authority.
Depends on PR 03 and PR 05 because unresolved effects share the exact execution
and Task dispatch/lock boundary; Task events still are not presentation
receipts. The review-only source diff is
7c08730f..8f30c02c on codex/ac-pr07-effect-journal.

## Owned surfaces

- Candidate generic schema/internal coordinator: openjiuwen/agent_teams/effect.py
  and schema/effect.py. Root exports are not implied by PR 07; PR 10 owns the
  bound public authority and raw DAO/Manager/token-bearing records are never
  public.
- Storage/runtime: tools/database/effect_dao.py,
  tools/database/__init__.py, tools/database/engine.py,
  tools/database/task_dao.py, tools/models.py and tools/task_manager.py.
- PR 03 quiescence/review-round authority, PR 05 runtime registration, Task
  incarnation, source events and Team deletion reservation, PR 06's possible
  internal continuation reuse and PR 10's public facade are affected dependency
  boundaries.
- PR 05's canonical `TaskEventEnvelope` writer/schema is an affected seam: PR
  07 owns one new generic effect-intent event type plus its atomic genesis-append
  tests, not the canonical event mechanism.
- Primary test:
  tests/unit_tests/agent_teams/test_execution_effect_journal.py.
- Historical candidate docs are F_87/S_29; allocate fresh names at replay
  (tentatively F_105/S_32).

## Contract

- EffectDao internally exposes plan, claim, purpose-typed authorization,
  result-bound receipt/observation finalization, settlement, verified read,
  reconciliation and claim reaping. Authority-free projections never contain a
  live claim/continuation secret.
- ExternalEffectCoordinator dispatches or observes only through a distinct,
  one-use authorization bound to the current fact head, exact registered
  execution phase/incarnation and adapter/provider namespace. A CALL token
  cannot write OBSERVATION, an OBSERVE token cannot write RECEIPT, and neither
  can fabricate evidence without the corresponding adapter boundary.
- Exact replay never appends a second fact or remints call authority.
- Expired dispatch is ambiguous, not safely retryable; wrong/stale/corrupt
  inputs have zero provider and journal effects.
- Planning atomically appends a PR 07-owned generic effect-intent
  `TaskEventEnvelope` through the accepted PR 05 canonical event writer with
  the effect genesis fact. That non-effect-table event is the durable
  existence anchor: if it exists while the journal/projection/fact rows or
  genesis binding are absent, every read-for-authority, provider call,
  reconciliation and Task mutation fails closed.
- Ordinary Task/Team clean preserves immutable effect history as session-domain
  tombstones; explicit session-domain destruction is the only removal path.
- Provider credentials, request interpretation, project/file probes,
  compensation selection and user confirmation remain downstream.

## Replay and verification

1. Rebase after PR 03 and PR 05; record both accepted SHAs.
2. Rebuild test_execution_effect_journal.py from the accepted contract, using
   `bead0a87` only as historical evidence. Do not restore its never-called
   receipt/observation positives as acceptance oracles. Run the rebuilt file
   before implementation and record red:

       uv run pytest tests/unit_tests/agent_teams/test_execution_effect_journal.py -q

3. From the exact accepted PR 03/05 tips, implement only the accepted effect
   delta with EffectDao as subordinate owner and no imports from LiveVoice or
   product adapters. Treat `398454d0` as historical evidence, not a commit to
   replay; PR 07 has no implementation dependency on historical PR 06.
4. Rerun the full primary file; repeat competing claims, dispatch/reset,
   one-use authorization and ambiguous-observation races.
5. Run supported-dialect dynamic-table compilation, file-backed SQLite
   reopen/corruption/rollback cases, changed-file Ruff, isolated Mypy for pure
   schema/coordinator modules, compileall and git diff --check.
6. Obtain Tier-3 review focused on provider-call zero effects, retry ambiguity,
   prefix integrity, continuation consumption and Task/effect transaction
   ordering.

## Replay preflight — 2026-08-25

Formal replay is blocked on accepted, packaged PR 03/05 tips and the contract
decisions below. The historical source/test/docs commits are `398454d0`,
`bead0a87` and `8f30c02c`; their range is read-only evidence and must not be
layered onto the technical PR 03 worktree or the historical PR 06 stack.

The historical implementation cannot be replayed mechanically. Reimplementation
must:

- split CALL and OBSERVE into purpose-specific, one-use continuations. Final
  authorization must consume the exact token under the reservation-aware Team
  lock while comparing current session/Team/Task incarnation/execution version/
  profile/generation/registered runtime/phase or review round and complete
  journal head/digest. The historical CALL check ignores its recorded prefix;
  OBSERVE performs a read-only rollback and can call the adapter repeatedly;
- make evidence provenance non-forgeable at the AgentCore boundary. A CALL
  completion may finalize only its returned receipt; an independently consumed
  OBSERVE completion may finalize only its returned observation. A CALL token
  must not append an observation or settle from one, a RECONCILE token must not
  append a receipt, and no token that was never consumed at the adapter boundary
  may append external evidence. The historical positive suite performs these
  never-called writes and must be rewritten;
- bind every continuation to the exact adapter/provider namespace and stable
  operation-key scope, not merely to a caller-supplied key. One semantic binding
  must own a stable provider key within that namespace; changed target/intended
  digest is a conflict. A checkpoint payload `put` may reuse only an internal
  purpose-typed primitive and must never acquire general provider-call authority;
- make the fact prefix and projection one reconstructible authority boundary.
  The authority-free lifecycle projection, origin execution binding,
  per-dispatch receipt/observation, claim purpose/version/expiry and
  continuation identity/consumption state must be derivable from and checked
  against immutable facts. Opaque live token bytes remain internal and are
  neither facts nor projections. Missing, extra or corrupt fact/journal/
  projection truth must block claim, authorization, reconciliation, Task token
  staling and provider calls, not merely make `read_effect_prefix` return none;
- atomically pair the first effect fact with a PR 07-owned generic effect-intent
  `TaskEventEnvelope` appended through the accepted PR 05 canonical writer in
  the shared TaskDao transaction. This event is the journal-external presence
  anchor, not a second effect-state owner: an
  anchor/genesis/head mismatch, including an anchor with every effect row
  missing, must fail closed. If formal design cannot preserve that atomic
  pairing, narrow the all-rows-missing claim before implementation rather than
  pretending deletion is detectable;
- record or otherwise immutably reconstruct CALL/OBSERVE authorization
  consumption. Historical `call_authorized_at` is mutable projection state and
  is erased by claim cleanup, so the final prefix cannot prove that the one-use
  boundary was consumed;
- bind receipt, observation and quiescence to an exact dispatch ordinal. A retry
  dispatch must clear/supersede older projection values atomically; an old
  `NOT_OBSERVED`/`call_quiesced` result cannot classify or authorize a later
  dispatch;
- remove live claim and continuation secrets from authority-free records and
  prefixes. Historical `get_effect` returns the live claim token and same-
  claimant replay returns it before exact version/owner validation. Claimant
  authority must be session/member/capability-bound rather than a caller-chosen
  string. Raw EffectDao/TeamTaskManager mutation surfaces stay internal; PR 10
  owns the only bound public construction path;
- preserve journals, projections and facts as session-domain tombstones across
  ordinary Task deletion and normal Team clean. Historical Team foreign keys
  cascade all three tables, exact replay first requires a live Team, and the
  effect lock ignores deletion reservation. Immutable replay/conflict lookup
  must run identity-first; every fresh writer/provider authorization must use
  the shared reservation-aware Team lock; only explicit session destruction
  removes history;
- extend PR 03/05 authority rather than the historical logical `owned` row.
  Planning, dispatch and provider authorization require PR 05's exact registered
  and quiesceable runtime plus Task incarnation/source-event identity. Review-
  originated effects bind the PR 03 exact round/phase; quiesce/cancel first
  fences new calls and cannot settle or delete while a provider outcome remains
  unresolved;
- enforce the fact-prefix bound before mutation. Historical append permits fact
  4097 and then makes the entire prefix permanently unreadable because the bound
  exists only in the reader. The final generic policy must reject the boundary-
  crossing append atomically or define a versioned paged/checkpointed prefix;
- require an explicit immutable compensation relationship. A later unrelated
  observed+settled effect in the same execution cannot retroactively become the
  compensation child merely because settlement names its ID; product selection
  stays downstream while the declared parent/child identity stays generic; and
- preserve current `DbSessions.write()` serialization/watchdog/retry behaviour,
  candidate-table snapshots, deletion-reservation migration and child-before-
  parent explicit session cleanup. No invalid path may mutate SessionFileStore.
  Dialect compilation does not replace real PostgreSQL/MySQL row-lock evidence.

Before rebuilding the red suite, freeze:

1. CALL, OBSERVE, result-finalization and settlement token identities, purpose
   separation, one-use consumption facts and crash semantics;
2. complete Task-incarnation/runtime/phase/source-event/prefix binding and how
   PR 03 quiescence fences a provider call;
3. adapter/provider namespace plus stable-key uniqueness and retry policy;
4. fact-to-projection reconstruction, corruption response, maximum-prefix
   behaviour and the PR 07 effect-intent event/genesis presence anchor;
5. normal-clean tombstones, identity-first replay and explicit session-domain
   destruction;
6. per-dispatch receipt/observation/quiescence supersession and immutable
   compensation-parent binding;
7. PR 10's bound public exports and the redacted internal/public record split;
   and
8. whether PR 06 consumes the accepted internal continuation primitive or keeps
   its strictly checkpoint-only reservation.

Tier-3 red/green evidence must rebuild, rather than copy, the historical cases
and add:

- real registered non-Voice runtime -> plan -> CALL authorization -> exact
  injected adapter -> receipt -> separately authorized OBSERVE -> observation ->
  settlement, with one verified prefix/projection and no raw public authority;
- concurrent double CALL and double OBSERVE consumption plus a stale
  authorization after another effect advances the shared prefix, proving one
  provider call/probe and zero stale effects;
- the complete wrong-purpose matrix and receipt/observation/settlement attempts
  without an actual adapter result, all with zero journal/provider/Task effects;
- wrong session/Team/Task incarnation/execution/version/profile/generation/
  registered runtime/phase/review round/source event/provider namespace/key/
  claimant/head/digest and a reserved Team across every authority-bearing path;
- provider authorization racing quiesce/reset/cancel/terminal settlement, PR 05
  dispatch resolution and normal Team clean in both lock orders;
- cancellation/crash before dispatch, after dispatch/before authorization,
  after authorization/before call, during/after provider call, before receipt,
  during observation and after settlement commit/before ACK, with truthful
  unknown/no-retry/exact-replay outcomes;
- retry dispatch R -> R+1 proving R's receipt/observation/quiescence cannot
  classify, settle or authorize R+1;
- missing/extra/corrupt fact, journal head/digest and projection/binding/claim/
  consumption state followed by claim/authorize/reconcile/Task mutation, with
  zero provider and forbidden mutation effects;
- PR 07 effect-intent `TaskEventEnvelope` with every effect journal row missing,
  and the inverse orphan journal without its event, followed by read, reset,
  settlement and provider authorization, all fail-closed with zero forbidden
  effects;
- live-claim reads and same-claimant replay proving no token leaks through an
  authority-free record and only the bound principal can recover an ACK-lost
  claim;
- stable provider-key exact replay/conflict, cross-provider namespace isolation,
  maximum/over-limit fact prefix, payload/identity bounds and distinct declared
  compensation child integrity;
- two independent `DbSessions` competing for operation ordinal, fact head,
  claim, CALL/OBSERVE consumption, settlement and Team deletion reservation;
- ordinary Task deletion and normal Team clean followed by prefix/read/replay and
  same-ID rebuild under the accepted incarnation policy; explicit session
  destruction alone removes all installed effect/attempt/command/event/dispatch
  tombstones, while later composition must include checkpoint tombstones without
  making PR 06 a PR 07 implementation dependency; and
- current write-locked SQLite migration/reopen/drop, root-export lock and
  supported-dialect DDL; rerun current `test_database.py`,
  `test_database_concurrency.py`, `test_db_sessions_watchdog.py` and
  `team_workspace/test_session_file_store.py` coverage for TeamDatabase
  hydration/update/graph/rollback and `DbSessions.write()` locking/watchdog.
  Every rejected or rolled-back effect path must byte-compare the applicable
  SessionFileStore tree before/after and prove zero change. Real
  PostgreSQL/MySQL behaviour remains an explicit non-claim when services are
  absent.

The independent preflight review reports **5 Critical / 6 Important** against
the historical candidate. These findings are replay requirements above, not
findings accepted into a formal branch. Historical closure counts and its prior
review do not transfer. Formal PR 07 branch readiness is **No**.

## Commit and PR package

Keep three consecutive commits: source, tests, then docs. Proposed title:
“feat(agent-teams): add a fenced external-effect journal”.

The PR body must describe EffectDao ownership, reconstructible lifecycle facts,
purpose-specific one-use continuation/result authority, the PR 10 public split
and restart/concurrency/corruption evidence. Exclude Jiuwen project/file
mutation logic, provider-specific probes, product compensation selection, Web
receipts and LiveVoice confirmation rules.
