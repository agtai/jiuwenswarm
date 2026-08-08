# D95 P3 D0 attempt binding and W2 restart-evidence repair — 2026-08-08

> Current Tier-3 implementation/review record for the P3 blocker found during
> the first real W2 cumulative rehearsal. This batch is **IN PROGRESS**, remains
> uncommitted, has not completed D-053 review, and grants no Gate or Replacement
> Ledger credit. [STATUS.md](STATUS.md) remains the only authority for mutable
> branch state and next action.

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

The first blocker has an uncommitted repair plus initial regressions. Independent
review found additional cancellation and cleanup ownership gaps, so that repair
is not accepted yet. D-069 now freezes the second blocker's bounded retry
contract, but it has no implementation, review or Gate evidence yet.

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

## 3. Current uncommitted repair scope

The working tree currently changes four production files and two test files:

- `jiuwenswarm/server/live_voice/project_code_executor.py` adds an exact attempt-executor
  lease, validates the isolated root, rechecks initialization side effects,
  releases the attempt Agent before patch capture/application, and retains
  cleanup ownership before deleting the checkout;
- `jiuwenswarm/server/live_voice/p3_authenticated_composition.py` supplies the production
  attempt lease and prevents global resolver cleanup while a D0 worker remains
  live;
- `jiuwenswarm/server/runtime/agent_manager.py` adds a dedicated attempt-Agent cache/pin
  boundary and exact identity release;
- `jiuwenswarm/server/runtime/agent_adapter/interface.py` begins a strict formal-project
  cleanup seam;
- `tests/unit_tests/live_voice/test_project_code_executor.py` adds exact-root positive/order and wrong-root
  zero-target-effect regressions;
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

## 4. Verification already run

These are development checks, not final acceptance evidence:

- before the new regressions were added, the three affected P3/AgentManager test
  files passed `122/122` under the repository `.venv`;
- the two newly edited test files then ran `62 passed, 1 failed`; the single
  failure is intentional exposure of a production mismatch—the attempt cache
  label is currently also passed as Code Agent `sub_mode="formal_attempt"`, while
  the established Code Agent must keep `sub_mode=None` and use only the cache key
  for isolation;
- Ruff passed for the two edited test files;
- `git diff --check` passes with only existing Windows line-ending notices.

No real P3 task has passed on this repair, no complete affected suite has run on
the final diff, and no D-053 pass is closed.

## 5. Open review findings before the attempt-binding repair can pass

The read-only lifecycle review found the following actionable blockers:

1. Exact release currently checks `has_session_runtime()` before strict cleanup;
   partial initialization therefore cannot be cleaned and can remain permanently
   pending. Strict cleanup must run first and quiescence must be verified after.
2. Release removes cache/pin ownership before an awaited cleanup and does not
   restore it on `CancelledError`. Ownership must remain retryable across both
   ordinary failures and cancellation.
3. Factory acquisition must hand cleanup ownership to D0 before any root getter
   or capability check that may fail.
4. The current facade strict-cleanup draft can clear `_adapter` before proving
   adapter runtime is gone; the formal path must propagate child cleanup failure
   and verify quiescence before discarding the adapter.
5. Channel-wide formal-Agent cleanup currently swallows failures and the resolver
   marks itself closed before cleanup succeeds. Both must remain retryable.
6. Code Agent initialization uses executor-backed work that is not stopped by
   cancellation of the awaiting coroutine. D0 must retain and await/shield the
   acquire task, obtain/release any eventual lease, and only then delete the
   checkout. Bounded close must expose cleanup-pending rather than globally
   tearing down a still-owned Agent.
7. `EXECUTOR_CAPABILITY_UNAVAILABLE` must remain a stable diagnostic rather than
   regress to generic `PROJECT_EXECUTOR_FAILED`.
8. The final test matrix still needs one composition test through the production
   resolver, AgentManager and real `JiuWenSwarm` facade with a controlled fake
   Code Adapter; an accept-any-root executor is not sufficient regression proof.

## 6. D-032/D-053 closure required for this Tier-3 batch

| Dimension | Required oracle before acceptance | Current state |
|---|---|---|
| Positive | exact detached-root Agent edits only the checkout; reviewed patch reaches only the canonical target | unit seam partial; real route not rerun |
| Negative | wrong/missing root or capability fails with stable reason and zero canonical/external mutation | initial wrong-root regression added |
| Boundary | HEAD/tree/support paths, one lease, one checkout and one exact cache identity remain bounded | partial |
| State | Agent release, worktree cleanup and business terminal truth remain separate and retryable | review findings open |
| Timing | cancellation during acquire, stream, release and apply cannot create late writes | acquire/release cases open |
| Concurrency | duplicate acquire and global close cannot steal a live attempt lease | partial/open |
| Recovery | cleanup failure retries Agent first, then worktree; process restart may clean only orphaned checkout | partial/open |
| Identity/security | canonical authority root remains canonical; the temporary root never becomes product identity | design preserved; composition proof open |
| Failure | initialization, stream, cleanup and worktree errors retain stable sanitized codes | partial/open |
| Compatibility | legacy/manual binding tests and feature-off behavior remain unchanged | earlier regressions pass; final rerun pending |
| Cross-module | production resolver → AgentManager → real facade → D0 → canonical patch | not yet covered or rerun |

After fixing all findings, run implementation self-review, a cold complete-diff
review and an independent review equivalent. Every finding must be fixed and its
affected tests rerun before a local implementation commit is accepted.

## 7. Accepted D-069 W2 P3 restart-evidence contract

The strict Gate implementation derives P3 Core only when one `task_id` has real
create/get/status/cancel/events plus list evidence. It derives P3 Executor only
when a completed D0 `task.attempt` uses that same Core `task_id` and the same task
also appears in a valid predecessor/successor restart chain. The acceptance
minimum is P3 `>=20/25`; without the six-point Executor item, the Core, Voice
Bridge, Progress and UI items total only 19.

The current formal Core and policy still implement only `task.create` and
`task.cancel`; the authenticated route, Store, subscription and Web consumer do
not yet implement retry. D-069 in [DECISIONS.md](decisions/DECISIONS.md) accepts a
bounded, explicit and exactly confirmed `task.retry` contract. It does not make
retry an automatic restart/recovery behavior and it does not grant implementation
or Gate credit.

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

Implementation and acceptance must proceed in this order:

1. close section 5's retained Agent/checkout ownership findings and its complete
   Tier-3 reviews without relaxing the exact-root or clean-worktree guards;
2. add the backend Store/Core atomic retry, reducer/event/subscription segment,
   policy/auth/confirmation, facade/composition/Gateway and reconciliation/outbox
   behavior together with migration, idempotency, concurrency and zero-effect
   tests;
3. update the Web TypeScript contract, formal control leaf, product activation
   and route-panel consumer in the same compatible batch so no producer can emit
   an event that the selected consumer silently ignores;
4. complete implementation self-review, cold complete-diff review and an
   independent review equivalent, fixing findings and rerunning affected suites;
5. run a disposable A→B diagnostic, create and verify the external clean fixture
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
3. Fix the eight attempt-binding review findings in section 5 without relaxing
   the real facade's exact-root guard.
4. Run the focused P3/AgentManager/facade/vertical suites, then complete all three
   D-053 review passes and fix every finding.
5. Implement accepted D-069 in its recorded backend/Web dependency order, then
   prove exact replay/conflict, bounded eligibility, clean-checkpoint separation,
   current-attempt subscription segments, restart reconciliation and every
   rejection's zero-side-effect oracle before review acceptance.
6. Commit the coherent reviewed local batch under the active D-063 exception;
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
