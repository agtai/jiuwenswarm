# OpenJiuwen OJ-G1-A execution ownership conformance packet

> Date: 2026-08-23
>
> Status: Tier-3 conformance evidence complete; scope prerequisite prepared
> locally; production OJ-G1-A implementation stopped at the shared-protocol
> re-scope boundary; no migration, replacement, deletion, product-acceptance or
> remote-ref credit

## Intended behaviour and dependencies

OJ-G1-A tests whether existing AgentCore TaskDao, AsyncToolRuntime,
Checkpointer, Journal and TeamScheduler modules can be composed through
test-owned Adapters to provide one durable execution owner, an admission fence
and exact Task-cancel-to-execution cancellation. It does not assume that the
local `d143b04b` scope candidate is based on the correct upstream maintenance
line.

The two bounded lanes may investigate in parallel, but their integration order
is fixed:

1. **Scope/upstream readiness** fetches current AgentCore refs, locates the
   maintenance line containing locked source `94e10cb6`, audits every public
   known-task-ID query or mutation, and proves cross-team rejection with zero
   event publication on the selected target branch.
2. **Execution ownership conformance** first tries a test-only composition of
   existing modules. It may identify a production schema/API gap only after a
   red test proves that the composition cannot meet the contract.

No AgentCore PR base or final commit is selected until lane 1 closes. The local
`d143b04b` remains evidence only and must not be pushed.

## Owner, risk and surfaces

Main is the sole integration, shared-semantics, documentation and Git-history
owner. Parallel workers are read-only. The JiuwenSwarm surface is limited to a
new module-level conformance test under `tests/integration/openjiuwen/`,
test-support Adapters if needed, this packet and the minimal STATUS update. A
later AgentCore change may touch only the selected maintenance-line owners
proven necessary by the tests.

This is Tier 3 because it crosses task authority, isolation, cancellation,
execution ownership and restart durability. Applicable D-032 dimensions are
P/N/S/T/C/R/I/K/X; boundary inputs and failure/fallback are exercised where an
owned API exposes them. Every unauthorized or cancelled mutating path must
assert zero Task, event, Tool and file side effects.

## Acceptance

1. current AgentCore refs and the exact target maintenance line are recorded;
2. Team B cannot query or mutate Team A's known task ID through any public
   applicable Task API, and all rejected mutations publish zero events;
3. accepted Task cancellation stops its related AsyncTool execution before a
   guarded side effect;
4. cancel and complete racing on one Task produce exactly one canonical terminal
   result and do not revive the loser;
5. after process-object recreation, every persisted `in_progress` Task has a
   resolvable execution owner or an explicit orphan/recoverable disposition;
6. a checkpoint whose profile or generation differs from admission intent
   cannot cause Scheduler dispatch;
7. focused tests distinguish already-composable behaviour from the minimum
   generic AgentCore schema/API gap; a thin Facade is preferred whenever the
   composition passes.

## Explicit exclusions and stop conditions

- no push, remote branch/tag/ref mutation or PR creation;
- no EventEnvelope, global ordering, cursor/ACK or D2 effect-receipt/reconcile
  work; those remain OJ-G1-B and OJ-G1-C;
- no real Agent, real file Tool, crash-process injection, migration, dual write,
  canary, legacy deletion or Live Voice replacement credit;
- no production subject/project authorization or Unicode/path policy inside a
  generic TaskDao;
- no claim that accepted cancellation rolls back an already-committed external
  effect;
- if satisfying an oracle requires a new shared protocol/schema/migration or a
  second production owner, stop and re-scope before implementing it.

TaskDao's unscoped compatibility path may remain only if repository evidence
shows that it is a trusted internal storage API. If business code can call it
directly, optional scope remains a bypass; the minimum upstream design must
make scoped access mandatory for business callers or separate an explicitly
trusted unscoped API.

## Upstream line and scope prerequisite result

Fresh fetches of `origin` and `hongxing1227` were read without checkout, push,
prune or remote mutation. The locked `94e10cb6` source belongs to the
0.1.16-post5-and-later line. It is contained by current `origin/develop`
`4f2c29c34899a45cec56a7d765fcc95e4002f60a`, `origin/br_0.1.17` and
`origin/br_v0.1.17.post1`; it is not contained by
`origin/br_0.1.16.post2.hotfix` or `hongxing1227/develop`.

The primary PR base is therefore `origin/develop@4f2c29c3`, the fetched default
integration line. The relevant TaskDao/TaskManager blobs still contained the
same defect there. A released-0.1.17 backport is a separate decision and is not
the primary base.

The incomplete `d143b04b` candidate was not pushed or reused. It was proven to
allow Team B to complete Team A's task and to attach Team A task endpoints to a
Team B dependency graph. The replacement local branch `codex/oj-g1-scope`
contains three consecutive commits on `origin/develop`:

1. `759fdf54` — `fix(swarm): enforce task team scope`;
2. `c6564a59` — `test(swarm): cover cross-team task isolation`;
3. `c2e958e7` — `docs(swarm): define task storage scope`.

The implementation makes team scope mandatory on TaskDao task-ID operations,
adds `(team_name, task_id)` to authoritative SQL/CAS predicates, scopes both
dependency endpoints, and updates every production direct caller. There is no
optional `team_name=None` business bypass. A 22-case manager/monitor matrix, a
20-case direct-DAO matrix and one API-signature contract all pass (`43 passed`),
with Task/dependency/review-vote/plan snapshots unchanged and event publication
zero for foreign scope. The final affected 10-file regression is
`552 passed, 14 skipped`. An independent review found the two initial evidence
gaps (manager-pre-read false confidence and review-round vote snapshots); both
were corrected and the narrow re-review closed them.

No commit above has been pushed, and no PR or remote branch has been created.

## OJ-G1-A executable results

The new module-level suite is
`tests/integration/openjiuwen/test_agentcore_g1a_execution_conformance.py`.
It loads the exact locked AgentCore dependency and uses real TaskDao,
AsyncToolRuntime, AgentStorage Checkpointer, Workflow Journal and TeamScheduler
surfaces. A module-autouse guard independently checks distribution version and
the `direct_url.json` commit even when this file runs without G0. Test helpers
provide in-memory KV persistence, fixture creation, effect recording, a thin
in-process Task/execution relation and a pre-dispatch checkpoint gate; they do
not implement an ExecutionRecord backend, lease, generation CAS, durable
relation registry or effect journal.

Normal strict-xfail execution produced:

```text
9 passed, 5 xfailed in 9.26s
```

The nine green cases prove only:

- TaskDao cancel/complete has one terminal winner;
- AgentStorage checkpoint facts survive wrapper/session recreation on the same
  in-memory backend, while Journal completed-prefix facts survive a real WAL
  reload;
- a thin exact-match checkpoint gate permits one valid Scheduler selection,
  real Task transition to `in_progress`, and one call to each recorded
  host/message edge;
- a thin in-process relation Adapter preserves the TaskDao single winner and
  couples the observed cancel-winning interleaving to cooperative AsyncTool
  cancellation with zero completion/effect;
- the same thin checkpoint gate rejects wrong profile, stale generation, wrong
  task, wrong scope and corrupt checkpoint before Scheduler activation, with
  zero Task/host/message/event effect.

Running the same file with `--runxfail` produced exactly:

```text
5 failed, 9 passed in 9.26s
```

Every failure is a business assertion after successful fixture setup:

| Gap | Direct observation |
|---|---|
| OJ-G1A-01 cancel settlement | the thin relation Adapter called `AsyncToolRuntime.cancel()` after accepted TeamTask cancellation, but that public call returned before the cooperative coroutine unwound |
| OJ-G1A-02 Runtime terminal/effect fence | `cancel()` returned before unwind; a coroutine that caught `CancelledError` returned an oversized result, after which Runtime-owned spill, `completed` revival and completion injection remained possible |
| OJ-G1A-04 restart owner | an explicit Task/execution binding recovered from AgentStorage, but the new AsyncToolRuntime had no owner and the recovered disposition remained `in_progress`, with no reconcile result |
| OJ-G1A-05 stale-after-validation | the thin Adapter validated generation 1 and blocked; generation advanced to 2 before release, yet the same Scheduler activation committed Task start because validation and CAS share no revision |
| OJ-G1A-06 duplicate identity | launching a second running AsyncTool with the same ID did not fail closed and replaced the registry/handle identity |

Exact commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -o addopts='' tests\integration\openjiuwen\test_agentcore_g1a_execution_conformance.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -o addopts='' --runxfail tests\integration\openjiuwen\test_agentcore_g1a_execution_conformance.py --tb=short
```

Every xfail is restricted to `AssertionError`, so setup, timeout, API and source
drift fail the suite instead of being swallowed as expected gaps. OJ-G1A-01,
-02 and -06 are public-surface oracles. OJ-G1A-04 and the stale -05 race are
explicit gap characterizations because locked AgentCore exposes no restart
reconcile or generation-aware admission seam to invoke; once those APIs are
selected, their implementation PR must reconnect or replace these two cases
with direct acceptance oracles rather than claiming automatic XPASS. Ruff and
compileall pass for the new test; `git diff --check` passes for the test and
packet changes. An independent review rejected the first draft's disconnected
checkpoint tests, direct Python file write, forced cancel winner, Task-field
assumption and private Runtime handle; all were removed before these results
were recorded.

## Minimum generic AgentCore gap proven by the tests

Thin composition is sufficient for static checkpoint mismatch rejection and
the tested cooperative relation/race path. It is insufficient for the five red
boundaries. The smallest generic upstream design now justified is:

1. one scoped durable `ExecutionRecord` protocol/backend with independent
   `execution_id`, generation/revision, owner/lease, profile/checkpoint
   relation, state/disposition and start/admit/terminal CAS, or an equivalent
   canonical backend that provides those semantics;
2. thin explicit relation Adapters between TeamTask, AsyncTool and checkpoint
   identities; the modules need not reuse one `task_id`;
3. AsyncTool duplicate guard, cancellation that settles actual coroutine
   unwind, monotonic terminal state, and post-cancel completion/spill/injection
   and effect-admission fences;
4. a per-task Scheduler admission/reconcile seam whose checkpoint validation
   and Task start consume the same execution revision/generation atomically;
5. restart reconciliation that resolves the exact durable owner or records a
   stable orphan/recoverable disposition.

The test evidence therefore triggers the packet's stop condition: this is a
new shared protocol/backend and touches multiple production owners. It must be
re-scoped as the minimum AgentCore OJ-G1-A implementation PR before production
code is written. D2 effect receipt/probe/reconcile remains OJ-G1-C; this packet
requires only that effects newly attempted after accepted cancellation are not
admitted.
