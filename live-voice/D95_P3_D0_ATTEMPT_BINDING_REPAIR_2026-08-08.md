# D95 P3 D0 attempt binding and W2 restart-evidence repair — 2026-08-08

> Tier-3 implementation/review record for the P3 blockers found during the first
> real W2 cumulative rehearsal. The exact-root runtime-ownership sub-batch is
> **CLOSED** in `7be485e8c` with D-053 equivalent independent review PASS. D-069
> same-task retry source work is **CLOSED** across the integrated Gate/Web/Core/
> product slices through `46616a138`; real A→B→C and restart evidence remain open.
> Nothing in this record grants Gate or
> Replacement Ledger credit. [STATUS.md](STATUS.md) remains the only authority for
> mutable branch state and next action.

## 1. Outcome at this checkpoint

P1 is no longer the active source blocker: the latest assisted run completed
recognition, committed JiuwenSwarm Agent text, complete user-heard synthesis and
automatic successor capture. The cumulative W2 candidate is still not ready to
freeze because the real P3 D0 Executor exposed two code-level blockers:

1. the detached attempt checkout and the Code Agent had different execution
   roots, so the real facade rejected every attempt before model/file-tool work;
2. the v2 Gate requires one exact task to prove Core create/get/list/status/
   cancel/events, a completed D0 attempt and cross-epoch restart reconciliation,
   but the public P3 mutation surface currently has only create/cancel and no
   repeatable same-task retry transition.

The first blocker is closed in reviewed source commit `7be485e8c`. The hardened
Gate is integrated as `decec4a79`, the compatible Web retry consumer as
`89237a075`, and its canonical delivery-terminal history follow-up as `99eb0453f`.
D-069 Core/Store was frozen in isolated candidate `8067e1387`, rebased onto
governance/integration base `b5f3cec8b`. Its first
independent review was NOT PASS with three P1 defects in schema authority,
durable attempt lineage and reconciliation epoch isolation; a later replay-seam
review also found that a fresh product process could not reconstruct a stored
retry from client-owned facts. The worker now implements all four repairs and
Opus's D-070 third round on predecessor candidate `ad7e36bc8` confirmed those
repairs but returned NOT PASS with zero P1 and two P2 findings. Candidate
`0c18810eb` fixed the stable-error rollback finding; Opus's exact-SHA final round
then withdrew the progress-baseline finding as unreachable and returned PASS
after independently running default-coverage focused `343/343`, wide `1313/1313`
and static checks. Product testing subsequently found a separate pre-existing
retry correlation write/read asymmetry. Candidate `8067e1387` adds Store-owned
fail-before-readiness rejection, replay-order and zero-effect regressions and
passes default-coverage focused `344/344`, wide `1314/1314`, static checks and
self/cold review. Opus reviewed this exact two-file delta, independently reran
default-coverage focused `344/344`, wide `1314/1314` and static checks, and
returned PASS with no actionable finding. Main integrated the exact Core tree as
`3a6b54842`. Product candidate `6aac859ad` then closed its predecessor's two P2
findings, passed GPT/Sol's pinned delta/final third round and was integrated by
Main as `46616a138`. The authenticated create/cancel product path now includes
bounded retry and executor readiness. No real A→B→C journey or cumulative Gate
evidence exists.

## 2. Real failure and root cause

The disposable registered fixture was clean and the formal confirmation/create
route reached durable Task/Attempt persistence. Three real D0 attempts then
terminated as `PROJECT_EXECUTOR_FAILED`. Reconstruction of the exact internal
failure found:

- `DirectProjectCodeExecutorAdapter` creates a detached Git worktree for the
  exact attempt and sends that checkout as `project_dir`, `cwd` and
  `trusted_dirs`;
- `AgentManagerProjectBindingResolver` had created the Code Agent against the
  canonical registered project root;
- `JiuWenSwarm.process_background_code_task_stream` correctly requires the
  requested root to equal the Code Agent's bound root and raised
  `EXECUTION_TARGET_NOT_BOUND: Code Agent root mismatch`;
- the D0 terminal-error mapping reduced that diagnostic to the generic persisted
  `PROJECT_EXECUTOR_FAILED`.

The security check is correct and must not be relaxed. Existing positive tests
used executors that trusted `request.params["project_dir"]` and therefore never
exercised the real facade's exact-root guard.

## 3. Closed exact-root ownership repair scope

Commit `7be485e8c` closes the coherent ownership batch across eight files:

- `jiuwenswarm/server/live_voice/project_code_executor.py` adds an exact
  attempt-executor lease and a stable cross-process attempt lock, validates the
  isolated root, rechecks initialization side effects, persists terminal/cleanup
  truth before releasing ownership and never deletes a checkout while a live or
  unknown predecessor may still touch it;
- `jiuwenswarm/server/live_voice/p3_authenticated_composition.py` supplies the production
  attempt lease and prevents global resolver cleanup while a D0 worker remains
  live;
- `jiuwenswarm/server/runtime/agent_manager.py` adds a dedicated attempt-Agent cache/pin
  boundary and exact identity release;
- `jiuwenswarm/server/runtime/agent_adapter/interface.py` and
  `interface_deep.py` implement strict formal-project cleanup, retain partial
  child initialization before the first await and keep ordinary TUI lifecycle
  compatibility separate from the formal fail-closed path;
- `tests/unit_tests/live_voice/test_project_code_executor.py` and
  `test_p3_authenticated_composition.py` add exact-root, transition-race,
  cross-process recovery, retryable close and production composition regressions;
- `tests/unit_tests/agentserver/test_live_voice_p3_agent_profile.py` adds cache, borrower, identity and cleanup
  restoration regressions.

The intended positive order is:

1. create and seed the detached checkout;
2. acquire a Code Agent bound to that exact checkout;
3. prove Agent initialization changed neither HEAD, Git-visible tree nor protected
   runtime-support paths;
4. run the bounded file-tools-only stream;
5. strictly quiesce and release the attempt Agent;
6. revalidate and capture the checkout patch;
7. apply the exact patch to the still-unchanged canonical project;
8. remove the checkout;
9. release the original authority binding.

No path may delete a checkout while Agent initialization or a session child can
still touch it. A release/cleanup failure must retain retryable ownership and
must produce zero canonical-project mutation.

## 4. Closed ownership-batch verification

These checks accept the source batch, not the W2 product journey:

- the three focused D95 files passed `154/154` on the final diff;
- the additional ordinary TUI/session lifecycle group passed `45` tests; one
  known pre-existing Windows test with a hard-coded POSIX cache key was excluded
  because it does not exercise the changed formal path;
- deterministic oracles covered live expired predecessors, completion-before-lock
  release, cleanup failure followed by successful close retry, real Deep/facade
  partial-init and cleanup failures, and RuntimeError/CancelledError retention;
- Ruff, production-file `py_compile` and `git diff --check` passed;
- implementation self-review, cold complete-diff review and a separated read-only
  equivalent independent review completed with zero remaining P1/P2 findings. It
  was not `/review`, and the same-machine/repository limitation is recorded.

No new real P3 task or W2 acceptance Gate ran on this repair.

## 5. Closed review findings for the attempt-binding repair

The lifecycle review found the following blockers; all eight are closed by
`7be485e8c` and the final regressions above:

1. Strict cleanup now runs before the post-cleanup `has_session_runtime()`
   quiescence proof, including partial initialization.
2. Cache/pin ownership remains observable and retryable across both ordinary
   cleanup failures and `CancelledError`.
3. Factory acquisition hands cleanup ownership to D0 before root getters or
   capability checks that may fail.
4. The facade retains `_adapter` until child cleanup succeeds and quiescence is
   proven; swallowed lower-layer failure is covered by the real Deep regression.
5. Channel-wide formal-Agent cleanup and resolver close retain pending ownership,
   aggregate failures and retry instead of declaring a false closed state.
6. D0 retains and shields Agent acquisition, obtains/releases any eventual lease
   and deletes the checkout only after exact ownership and OS-lock quiescence.
7. `EXECUTOR_CAPABILITY_UNAVAILABLE` remains a stable diagnostic rather than
   regressing to generic `PROJECT_EXECUTOR_FAILED`.
8. The matrix includes production resolver → AgentManager → real `JiuWenSwarm`
   facade → controlled Code Adapter → D0 composition coverage; an
   accept-any-root executor is not treated as sufficient proof.

## 6. D-032/D-053 closure for the exact-root ownership batch

| Dimension | Required oracle before acceptance | Current state |
|---|---|---|
| Positive | exact detached-root Agent edits only the checkout; reviewed patch reaches only the canonical target | automated source oracle PASS; real route not rerun |
| Negative | wrong/missing root or capability fails with stable reason and zero canonical/external mutation | PASS |
| Boundary | HEAD/tree/support paths, one lease, one checkout and one exact cache identity remain bounded | PASS |
| State | Agent release, worktree cleanup and business terminal truth remain separate and retryable | PASS |
| Timing | cancellation during acquire, stream, release and apply cannot create late writes | PASS |
| Concurrency | duplicate acquire and global close cannot steal a live attempt lease | PASS |
| Recovery | cleanup failure retries Agent first, then worktree; process restart may clean only proven-orphan checkout | PASS within the frozen single-runtime/OS-lock boundary |
| Identity/security | canonical authority root remains canonical; the temporary root never becomes product identity | PASS |
| Failure | initialization, stream, cleanup and worktree errors retain stable sanitized codes | PASS |
| Compatibility | legacy/manual binding tests and feature-off behavior remain unchanged | affected regression PASS |
| Cross-module | production resolver → AgentManager → real facade → D0 → canonical patch | automated production composition PASS; real route remains open |

This table closes only the exact-root ownership source batch. D-069 Core/product
implementation and real W2 evidence keep their own independent review and Gate
requirements.

## 7. Accepted D-069 W2 P3 restart-evidence contract

The strict Gate implementation derives P3 Core only when one `task_id` has real
create/get/status/cancel/events plus list evidence. It derives P3 Executor only
when a completed D0 `task.attempt` uses that same Core `task_id` and the same task
also appears in a valid predecessor/successor restart chain. The acceptance
minimum is P3 `>=20/25`; without the six-point Executor item, the Core, Voice
Bridge, Progress and UI items total only 19.

D-069 in [DECISIONS.md](decisions/DECISIONS.md) accepts a bounded, explicit and
exactly confirmed `task.retry` contract. D-070 fixes the two-batch execution and
review split: GPT/Sol implements Core and reviews Opus's product batch; Opus
performs Core's third round and implements product reachability; Main alone
integrates. Gate derivation, the Web consumer and reviewed Core/Store are
integrated, but the authenticated product route has no accepted retry extension
yet. This does not make retry an automatic restart/recovery
behavior and grants no Gate credit.

Current slice evidence at this checkpoint:

- Gate `decec4a79` completed self/cold/separated independent-equivalent review;
  its focused Gate/CLI suite passed `77/77` before integration;
- Web `89237a075` and follow-up `99eb0453f` completed the same three passes;
  Python/TypeScript contract tests passed `32/32`, integrated Web tests `201/201`,
  and frontend `tsc --noEmit` passed again on the integration branch;
- Core/Store candidate `8067e1387` contains the independent review's three P1
  repairs, the later durable applied-replay repair and the Opus F-3 rollback-error
  correction plus the later correlation admission repair. On parent `b5f3cec8b`,
  repository-default-coverage focused tests pass `344/344` in 95.46 seconds,
  wide tests pass `1314/1314` in 185.24 seconds, and format/Ruff/compile/diff
  checks pass. Opus returned PASS on exact predecessor `0c18810eb`, then confirmed
  the `62+/1-` correlation delta at exact SHA `8067e1387` with no actionable
  finding after independently rerunning the same `344/344` focused and `1314/1314`
  wide suites. Main integrated the exact 14-file Core tree as `3a6b54842`;
- the isolated product branch repaired both P2 findings in exact candidate
  `6aac859ad` on Core integration `3a6b54842`. GPT/Sol's pinned delta/final third
  round independently matched the commit, tree and all twelve blobs; reran the
  four new deterministic regressions, default-coverage focused `341/341`, a
  final wide `1379/1379`, Ruff, compile and diff checks; and returned `PASS` with
  no actionable finding. The first wide run had one failure in an unchanged P2
  rollback timing test; that exact case passed `5/5` in isolation and the second
  wide run was fully green. Main integrated the exact product tree as
  `46616a138`. W2 uses the existing
  `live_voice.composition.p3.mutate` carrier, so a separate
  `live_voice.task.retry` ReqMethod/Gateway/AgentServer route is not part of this
  batch.

### 7.1 Normalized Core/Store independent-review findings

The machine-local review scratchpad is recovery material only and is not a Git
authority. The following stable findings are reconciled against the worker diff
and reported deterministic tests; historical line numbers and superseded
transcript inferences are intentionally omitted. Their implementation status is
not acceptance: the rebased exact candidate still needs Opus review.

1. **Schema authority failed open at construction.** A database containing only
   generic/shared metadata could claim the Task Store v2 version without the
   required tables, columns, constraints and indexes, so construction succeeded
   and the first operation failed later. The repair validates the exact owned v1
   topology before migration and the complete v2 topology at startup; unsupported
   or corrupt ownership fails with zero DDL, while unrelated component tables may
   coexist.
2. **Retry admission did not prove the existing durable lineage.** A corrupted B
   `task.retry_accepted` predecessor binding could still authorize B→C and reach
   outbox claim/snapshot consumers. The repair makes one strict verifier serve
   read authority and transaction re-CAS, proving contiguous attempt ordinals,
   unique create/retry boundaries, exact command/result/dispatch/spec bindings,
   eligible predecessor terminal truth and settled authority before any mutation
   or readiness call.
3. **Reconciliation publication crossed or aborted on attempt epochs.** An open
   post-transaction task-global event read could publish C's retry boundary with
   B's attempt after concurrent retry; a stale B callback could also abort the
   wider restart audit instead of being recognized as superseded. The repair
   returns the transaction's frozen attempt/event receipt, publishes only that
   receipt, and treats exact old-attempt callbacks as an explicit superseded
   no-op while unknown failures remain fail closed.
4. **Applied-retry replay required server-derived request facts.** The first seam
   expected a caller to retain the complete original `CommandEnvelope`, including
   predecessor/outcome/ordinal values a fresh product process cannot reconstruct
   after the task advances. The repair exposes Core read-only authority/replay
   seams keyed by authenticated scope, task/command identity and one exact
   product-owned opaque request fingerprint; Store reconstructs and verifies the
   canonical command/result/lineage internally. A reopened process can replay B
   after C with zero database, readiness or Executor effect, while changed
   client-owned facts conflict.
5. **Retry correlation could be committed with inconsistent durable identity.**
   Store admission accepted a retry command whose correlation differed from the
   authoritative task, persisted that command, and emitted the retry boundary
   with the task correlation; later lineage reads then classified the task as
   corrupt. Candidate `8067e1387` rejects the mismatch as
   `TASK_RETRY_PRECONDITION_STALE` before readiness or any write, preserves the
   healthy lineage and zero-effect oracle, and keeps exact replay/conflict
   classification ahead of current-state admission.

The worker's current regressions cover malformed or partial schemas, lineage
corruption, cross-process replay without the original envelope, reconciliation
commit→retry→publish races, superseded status races, current-attempt outbox/
cancel/reconciliation behavior, attempt-segment subscription/progress and
concurrent retry CAS. D-070's Core acceptance boundary is now closed: Opus
confirmed the correlation delta on frozen candidate `8067e1387` with the supplied
exact commands, and Main integrated that exact tree as `3a6b54842`.

Each preview/candidate handoff to Opus must carry the exact SHA, worktree cwd,
Python executable, focused and wide commands, expected collection/result and
coverage mode. Iteration or single-failure diagnosis may use `--no-cov`, but it
cannot substitute for the formal third-round focused/wide run with the repository
default coverage configuration; the wide review window must allow for that cost.

### 7.2 Opus third-round findings and `0c18810eb` disposition

The D-070 cross-model third round was a separated read-only review rather than a
literal `/review`; it retains the recorded same-machine/same-repository
limitation. Opus reran the supplied default-coverage suites (`342/342` focused,
`1312/1312` wide) and static checks itself. It confirmed the earlier P1 repairs,
found zero new P1 defects and returned NOT PASS on two P2 items:

1. **F-2, progress baseline — WITHDRAWN / NOT APPLICABLE:** the review inferred that a tracker receiving a
   non-initial attempt segment had no entry point to seed its nonzero progress
   sequence and might buffer B/C output indefinitely. The semantic follow-up
   found that the generic `EventSequenceTracker` is not the P3 product
   current-segment consumer: its only Python production construction is the Agent
   bridge's complete producer stream. The product path constructs
   `TaskProgressReturnBridge`; text origin binds the first received event sequence,
   while exact authority origin reads `segment_start_seq`, attempt identity and
   ordinal from the atomic subscription snapshot and begins a verified arbiter
   attempt epoch on `task.retry_accepted`. The deterministic
   `test_retry_segment_projects_from_authority_owned_nonzero_baseline` covers a
   fresh B subscriber whose boundary is greater than zero and observes no gap or
   out-of-order event. Opus's exact-SHA review also confirmed that production
   `TaskProgressOriginKind.VOICE` occurrences are rejection branches, not a
   constructed product bridge, and withdrew the finding without a protocol
   change.
2. **F-3, rollback error stability — CLOSED:** `_initialize()` called `rollback()` directly
   while handling an already-stable schema rejection, so a rollback failure could
   replace the authoritative `FormalTaskViolation`. Candidate `0c18810eb` retains
   the primary error even if rollback itself fails. A failure-first regression
   proves `TASK_STORE_SCHEMA_UNSUPPORTED`/`UNSUPPORTED` and byte-identical database
   state with an injected rollback exception.

Opus independently reran default-coverage focused `343/343`, wide `1313/1313`
and all supplied static checks on pinned detached candidate `0c18810eb` and
returned PASS with no actionable new finding. The later correlation finding is a
separate delta now frozen in `8067e1387`.

### 7.3 Product-worker state and formatting boundary

The Opus product worker is isolated on `claude/w2-task-retry-product`. Exact
candidate `6aac859ad` is rebased onto accepted Core integration `3a6b54842` and
contains six production files and six direct test files for executor readiness
plus policy/auth/confirmation/composition retry handling. Its self/cold review
and GPT/Sol cross-model third round are `PASS`; Main integrated its exact twelve
blobs as `46616a138`.

The predecessor third round on `8bba26cb0` found two actionable P2 defects. First,
`_validate_product_p3_mutation_params` includes `auth_token` in its structural
required-field set, so an absent bearer returns
`INVALID_PRODUCT_COMPOSITION_ARGUMENT / INVALID_ARGUMENT` before the existing
authenticator can preserve `FORMAL_TASK_AUTHENTICATION_REQUIRED /
UNAUTHENTICATED`, contrary to D-069's stable authorization reasons. Second,
`DirectProjectCodeExecutorAdapter.retry_readiness` treats every absent attempt
journal as `ATTEMPT_JOURNAL_MISSING`. Core's canonical cancel-before-dispatch
path intentionally produces a terminal cancelled attempt with
`cancel_requested=true`, `dispatch_fenced=true`, `executor_ref=None`, no
Executor dispatch and therefore no journal; that exact predecessor is eligible
under D-069 once Store-owned outbox/reconciliation checks pass. The repair must
admit only that complete shape and keep every other missing-journal case fail
closed. Both fixes require positive, forged/incomplete-shape and zero-effect
tests plus repeated self/cold and GPT/Sol delta/final review. Candidate
`6aac859ad` closes both defects: structural validation keeps `auth_token` allowed
but leaves its absence to the authenticator, and Direct Executor readiness admits
only the complete canonical cancelled-before-dispatch shape while every degraded
or divergent missing-journal shape remains not ready. The product-level
create→cancel-before-dispatch→retry regression creates exactly one successor.

The two environments continued to produce different stable patch-id values for
the same diff. Candidate `6aac859ad` resolved identity through stronger content
facts instead: both sides matched commit `6aac859add1075021f71654f33db1f936fd1c6d3`,
tree `79aef03edccdd6a03de7878403cd0c51aad0875f` and all twelve blob IDs. The
patch-id difference is therefore recorded as a Git-environment rendering
difference, not a candidate-integrity or code finding.

The accepted W2 carrier is the existing authenticated
`live_voice.composition.p3.mutate` method with `operation=task.retry`. A separate
`live_voice.task.retry` method would require a new public `ReqMethod`, Gateway
allow-list and AgentServer dispatch surface but is not used by the integrated Web
consumer. It is scope-out for this batch: remove the dead mapping from
`P3_ROUTE_METHODS`, keep internal operation validation explicitly aware of
`task.retry`, and do not add the direct transport route.

Formatting is not an authority to rewrite protected history. Before running a
whole-file formatter on any allowed product file, the worker must first test that
exact file on the clean pinned base and record whether it is already format-clean.
`project_code_executor.py` is not format-clean on the current base and must never
receive a whole-file `ruff format` during this batch. Its retry addition must stay
narrowly formatted and `ruff check`-clean without changing unrelated lines. The
same rule applies to any other baseline-dirty file: reject unrelated formatter
output and reapply a narrow change. In particular, formatting must not touch
`_AttemptOwnershipLock`, worktree handling, journal state, exact-root, attempt
lease, cross-process lock or retained cleanup/release semantics closed in
`7be485e8c`.

The deterministic evidence topology has exactly three distinct attempts:

- attempt A is created, queried and successfully cancelled, proving the Core
  create/get/list/status/cancel/events path and a real cancelled terminal;
- the first retry creates attempt B without changing `task_id`; B completes its
  D0 mutation and supplies the successful `task.attempt` fact;
- after B, the external W2 fixture harness verifies the patch and records a new
  clean Git revision for the same `{source, stable_id, uri, scope}` project
  identity; retry itself performs no Git operation and cannot weaken the clean
  guard;
- the second retry creates attempt C with the same `task_id` against that exact
  clean revision; the predecessor records C nonterminal and closes normally,
  then the successor publishes truthful reconciliation for exact C;
- the Gate joins Core, B's D0 fact and C's restart by exact same `task_id`, while
  restart reconciliation itself remains exact on both C's `task_id` and
  `attempt_id`.

The Store-derived budget is three total attempts/two applied retries. Only the
current terminal `cancelled` or `completed` attempt is eligible. Exact auth,
capability, confirmation, predecessor/outcome/next-number, same-project clean
revision and settled outbox/reconciliation/worker/lease/cleanup prerequisites
must all pass before one atomic CAS creates the successor. Applied exact replay
returns the stored result with zero new effect; changed fingerprints, stale
predecessors, exhausted budget and pending cleanup fail with the stable D-069
reason and the complete zero-side-effect oracle.

Each retry emits a new canonical `task.retry_accepted` (`state=accepted`) whose
details bind `command_id`, `retry_of_attempt_id`, `previous_outcome` and
`attempt_number`. Initial A alone begins with `task.accepted`. Full A/B/C history
is available only from `task.events`; a formal subscription starts from the
current attempt's atomic segment boundary (`task.accepted` for A, latest
`task.retry_accepted` for B/C). Consumers that have not negotiated the new event
must fail closed instead of skipping or translating it. Terminal irreversibility
therefore remains per attempt epoch rather than being weakened globally.

Implementation and acceptance proceed in this order:

1. section 5's retained Agent/checkout ownership findings and Tier-3 reviews are
   closed in `7be485e8c` without relaxing exact-root or clean-worktree guards;
2. the Gate and Web slices are integrated in `decec4a79`, `89237a075` and
   `99eb0453f`;
3. Core candidate `8067e1387` passed Opus's exact-SHA delta review and Main
   integrated its exact tree as `3a6b54842`;
4. Opus's rebased product candidate `6aac859ad` repaired the two findings in
   section 7.3, completed self/cold review, passed GPT/Sol's pinned delta/final
   third round and was integrated by Main as `46616a138` without reopening Core
   or `7be485e8c` ownership semantics;
5. Main's cumulative Contract/Core/Executor/product/route/Gate smoke passed
   `602/602`; run a disposable A→B diagnostic, create and verify the external clean fixture
   checkpoint, run C across the exact predecessor/successor process set, and
   reject any extra attempt or cross-task join;
6. only then create a fresh immutable candidate and run the hardened Gate with
   exact A/B/C task/attempt lineage and the separately signed root policy.

For planning only, the current three-showcase v2 evidence shape needs seven
runtime slots: `gw1/as1`, `gw2/as2` and `gw3/as3/as4`. The fourth AgentServer
slot is the successor needed for exact C restart observation. D-069 freezes the
attempt topology, not these slot names or their external authority bindings;
policy still has to be produced, signed and validated before evidence processes
start.

## 8. Machine-private continuation facts

These facts are usable on the current machine but are not restored by Git:

- isolated runtime data root:
  `D:\XGG AI\openjiuwen\jiuwenswarm-data-live-voice-w2-clean-20260808-1040`;
- persistent Session: `sess_19fe0b6fa94_893a8e5a2ee8`;
- registered project: `proj_fcdbd43e`;
- selected model: `deepseek-v4-flash`;
- disposable fixture:
  `D:\XGG AI\openjiuwen\jiuwenswarm-live-voice-w2-fixture-20260808-hongx`,
  baseline `d2790e7f35413e54979c02e9fa6d8fb6c18952e3`, clean at the last inspection;
- OpenAI Speech configuration and devices are ready; the key remains process
  environment/private input only and is not recorded here. Replacing the current
  Gateway may require the user to enter it once more through the hidden terminal
  prompt; never request or paste the key in chat, a command line, Git or evidence;
- deterministic user recording inputs are stored outside Git under
  `D:\XGG AI\openjiuwen\jiuwenswarm-live-voice-w2-input-20260808-hongx`:
  - `voice-command-48k-mono-pcm16.wav`, 48 kHz/mono/PCM16, 4523ms,
    SHA-256 `4df35a6ceb9ca44dc033e74f7700fe476af3705a74580b2fb66156bcf4a58557`;
  - `voice-command-16k-mono-pcm16.wav`, 16 kHz/mono/PCM16, 4523ms,
    SHA-256 `14fcf370fd0a3aefb4cf3ae43392c8cc35c900921d4296b6b478ec7b01d0f215`.

The WAV files pass the repository `inspect_pcm16_mono_wav` boundary. They may
drive repeatable STT and cumulative-route diagnostics but do not replace final
microphone/device evidence or the user's complete-playout receipt.

Existing service processes and detached candidate worktrees predate this repair
and are diagnostic only. Do not count them as Gate evidence. The candidate must
be recreated as one clean descendant after both P3 blockers and D-053 review
close.

## 9. Implementation checklist when STATUS routes the current slice here

This checklist does not own current priority; a new Session must follow
[STATUS.md](STATUS.md) first and use these steps only while STATUS still routes
the active slice to D95.

1. Read `live-voice/README.md`, `live-voice/STATUS.md`, this record, the W2 packet,
   Integrated Demo acceptance and the relevant P3 source/tests.
2. Run `git status --short --branch`, `git rev-parse HEAD` and upstream divergence;
   preserve every existing working-tree modification and do not overwrite
   user-owned or parallel work.
3. Treat section 5's exact-root ownership repair as closed at `7be485e8c`; do not
   reopen or refactor it unless an affected D-069 regression proves necessary.
4. Core `8067e1387` and product `6aac859ad` are accepted historical candidates;
   Main integrated their exact trees as `3a6b54842` and `46616a138`. Do not reopen
   their protocol, ownership or carrier semantics during diagnostic work.
5. Main cumulative integration smoke is `602/602 PASS`; next prove exact
   replay/conflict, bounded eligibility, frozen confirmation, clean-checkpoint separation,
   current-attempt subscription segments, restart reconciliation and every
   rejection's zero-side-effect oracle on the disposable real A→B→C diagnostic.
   Keep the W2 carrier on `live_voice.composition.p3.mutate`; do not add a direct
   retry ReqMethod, Gateway allow-list or AgentServer dispatch route.
6. Commit coherent reviewed local batches under the active D-063 exception;
   do not update any remote ref without separate exact user approval.
7. Create one fresh clean descendant candidate and a disposable diagnostic
   runtime. If the in-memory Speech credential is unavailable, ask the user for
   one hidden terminal re-entry. Run automated STT with the prepared WAV, then
   P2 Agent/Tool and P3 text smokes. After they pass, discard that runtime, create
   fresh Gate runtime/evidence roots and the complete seven-slot policy, obtain
   the user's external root signature plus expected-root hash acknowledgement,
   and validate the policy before any evidence owner or Gate process starts.
8. Run the controlled browser/fault/restart Gate only after policy preflight.
   Ask the user for final microphone capture, complete audible playout and the
   three exact showcase receipts; do not postpone root signing to this stage.
