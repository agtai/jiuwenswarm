# P3 Authenticated Composition Implementation Review — 2026-08-05

## Review identity

- Task: `P3-AUTH-COMPOSITION`
- Branch: `codex/lv-p3-auth-composition`
- Base: `1e76dbd6aa0ebb011842f31beb98ca2cb11d2496`
- Integration Owner reviewed candidate:
  `f20f00513cfab40551ba9a4f8858b7c747d483b5`
- Owner result for that candidate: `CHANGES REQUIRED`
- Risk: D-046 Tier 3 (authentication, authorization, durable mutation,
  reconciliation, concurrency, model/runtime binding, and workspace authority)
- Repair state: all changes after `f20f005` remain intentionally uncommitted under
  the unattended coordination rule; no Gate acceptance has been claimed.

This record covers only the P3-alpha authenticated composition. It does not
claim TC-C subscription, VB-C, CR notification, final UI composition,
Integrated Demo readiness, real-provider evidence, or Replacement Ledger
credit.

## Integration Owner findings and repair

1. **Confirmation authority (P1).** Browser `confirmed` is no longer accepted.
   A server-owned verifier must independently bind principal, exact scope,
   operation, command, target, canonical create intent, resolved model identity,
   config version, and expiry. `SqliteP3ConfirmationLedger` consumes a record
   transactionally and permits only the exact idempotent replay; forged,
   cross-bound, expired, and conflicting replays fail before Task Store, outbox,
   Executor, or Agent effects. The production factory accepts an injected trusted
   verifier. Because this repository has no trusted confirmation issuer/owner,
   AgentServer intentionally supplies none: queries can start, while create and
   cancel fail closed. Telemetry now says query route ready and mutation route
   closed rather than claiming the full mutation route is ready.
2. **Operation-aware clean worktree (P1).** Clean Git state is required only for
   create admission and actual dispatch. Get/list/status/events/exact cancel
   still revalidate authenticated scope, session/project/path, revision, expiry,
   and redaction but tolerate task-created dirtiness. A false clean-reader return
   is explicitly rejected. Dispatch performs a second authoritative clean,
   revision, scope, redaction, expiry, and model/config check immediately before
   carrier handoff.
3. **Crash/restart truth (P1).** An orphaned `origin_namespace=live_voice`
   running carrier row becomes `interrupted` with stable reason
   `FORMAL_EXECUTION_LOST_ON_PROCESS_RESTART`; legacy rows preserve `failed`.
   Core projects the original formal attempt as
   `TerminalOutcome.INTERRUPTED` without a new attempt, redispatch, or cancel.
4. **Reconciliation interval (P2).** Constructor and factory both require a
   finite value in `(0, 3600]`; `nan`, infinities, zero, negatives, and values
   above 3600 fail closed.
5. **Exact model resolution (P2).** Unknown or ambiguous explicit model intents
   fail closed. Admission persists the resolved canonical identity and whole
   catalog config fingerprint without constructing a model. Dispatch and its
   final handoff fence validate both before model/Agent/carrier effects. Multiple
   model names may legitimately each have a per-name `is_default`; the server
   default is the unique default variant in the first configured model-name
   group. Reorder/default/config drift is rejected.
6. **Review record.** This record identifies the reviewed commit, Owner result,
   repair diff, exact review substitutes, commands, results, and evidence limits.

## Additional independent-review repairs

The post-repair independent equivalent also found lifecycle races. Start/stop
are now serialized; concurrent starts create one worker; stop cannot be followed
by accidental reactivation. Shutdown first fences new routes, drains admitted
handlers (including cancellation while a submitted thread is still running),
performs a final durable reconciliation, cancels/drains the background worker,
and only then closes carrier scheduler/contexts and formal Agents. Agent and
model setup is followed by the dispatch handoff fence, and failed handoff
releases the pinned Agent without invoking the carrier.

## Owned contract and exclusions

The default-off route covers authenticated `task.create`, `task.get`,
`task.list`, `task.status`, `task.cancel`, and `task.events`. Browser input may
select a persisted session and provide business fields, but cannot assert a
principal, project, scope, AuthorizationContext, ContextRef, confirmation, or
resolved model binding. Formal support/Store files remain in the application
workspace; governed execution artifacts remain Git-visible target-project
changes.

The batch does not expand D-031 legacy authority, add TC-C subscription, run a
real side-effecting task, add UI/notification composition, modify shared ACG or
schema, update `STATUS.md`, or grant Gate/Replacement Ledger credit.

## D-046 scenario evidence

- Positive: exact-scope create/get/list/status/cancel/events, exact confirmation,
  idempotent replay, startup/periodic reconciliation, and carrier projection.
- Negative/zero effects: unauthenticated, wrong scope/session/project/revision,
  expired/redacted context, forged/cross-command/cross-task/cross-principal
  confirmation, expired/conflicting replay, dirty create/dispatch, unknown or
  drifting model, corrupt Store, and flag-off all reject at the reviewed
  boundary. Forbidden Task Store/outbox/Executor/Agent effects are asserted zero
  where applicable.
- Concurrency/restart: concurrent create/cancel replay, cancel race,
  confirmation replay across ledger restart, formal process-loss interruption,
  legacy failed compatibility, concurrent start/stop, cancelled blocking route
  drain, and final shutdown reconciliation.
- Resources: reconciliation worker, carrier scheduler, execution contexts,
  formal Agent pins, and Agent instances are closed; SQLite connections are
  operation-scoped.

## D-053 review passes

### 1. Implementation self-review

The repair diff was checked against the six Owner findings, Task Packet,
`AGENTS.md`, routed decisions/ACG sections, existing foundation behavior, and
actual tests. Findings fixed during this pass included list-wide persisted
context revalidation, lazy model construction, flag-off avoiding eager model
imports, and a dispatch-dirty zero-side-effect regression.

### 2. Cold complete-diff review

The complete tracked and untracked diff was reread against the original request
and directly affected interfaces. After the independent fixes and mechanical
formatting, the complete diff was reviewed again. The final pass found and fixed
the per-model versus global-default interpretation described above. No remaining
actionable finding was identified in the owned scope.

### 3. Independent review equivalent

`/review` was not available as an in-app command. A first exact CLI review was
started with:

```text
C:\Users\hongx\.codex\.sandbox-bin\codex.exe review
  -c 'sandbox_mode="danger-full-access"' --uncommitted
```

Codex CLI 0.146.0 used independent `gpt-5.6-sol` xhigh review context. It kept
making verifiable repository progress but produced no final result within the
bounded window; it was interrupted and is not claimed as a successful review.
Its 2.9 MB local log is retained as
`%LOCALAPPDATA%\Temp\lv-p3-auth-composition-review-fixes\independent-review.log`.
A second read-only tool-driven attempt was also terminated after five minutes
without a final result and is not counted.

The successful reproducible independent equivalent supplied the complete
tracked diff plus the full two untracked source files on stdin, prohibited tool
calls, and required findings-only output:

```text
PowerShell: instruction + git diff --no-ext-diff --unified=40
  + full p3_confirmation.py + full p3_model_resolution.py
  | C:\Users\hongx\.codex\.sandbox-bin\codex.exe exec
      --ephemeral --skip-git-repo-check
      -c 'model_reasoning_effort="high"'
      -o %LOCALAPPDATA%\Temp\lv-p3-auth-composition-review-fixes\independent-payload-review-final.txt
      -
```

It used independent `gpt-5.6-sol` high reasoning and returned five findings:
missing production confirmation owner, unsynchronized lifecycle, undrained
submitted mutation work, ignored false clean-reader return, and a dispatch
handoff TOCTOU. The four implementation findings were fixed and tested. The
first was resolved according to the Owner's explicit rule: without a trusted
issuer, production mutations remain closed; only the misleading readiness log
was corrected. Limitation: the successful pass reviewed the complete patch
payload but could not independently browse interfaces outside that payload;
the two earlier read-only attempts inspected those interfaces but had no final
result. This entry is an independent equivalent, not a claim that `/review`
succeeded.

## Verification

Repository venv:
`D:\XGG AI\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe`

Final affected regression command:

```text
python -m pytest --no-cov -q
  tests/unit_tests/live_voice/test_p3_authenticated_composition.py
  tests/unit_tests/live_voice/test_formal_task_policy.py
  tests/unit_tests/agentserver/test_live_voice_p3_agent_profile.py
  tests/unit_tests/agentserver/test_live_voice_p3_route.py
  tests/unit_tests/auto_harness/test_schedule_task_service.py
  tests/unit_tests/live_voice/test_project_code_executor.py
  tests/unit_tests/live_voice/test_persistent_task_core.py
  tests/integration/live_voice/test_formal_task_executor_adapter.py
  tests/unit_tests/test_app_web_handlers.py
  tests/unit_tests/agentserver/test_agent_ws_connection_close.py
  tests/unit_tests/agentserver/test_agent_manager_session_cleanup.py
  tests/unit_tests/server/test_agent_history_gitignore.py
  tests/unit_tests/gateway/test_agent_client.py
  --deselect tests/unit_tests/agentserver/test_agent_manager_session_cleanup.py::test_same_key_creation_waits_for_old_root_cleanup
```

Result: `371 passed, 1 deselected, 1 warning in 22.38s`. The deselected timing
test fails on clean BASE_SHA as previously recorded; the warning is the installed
`fastmcp` Authlib deprecation warning. A focused composition/executor/real-carrier
run also passed: `73 passed in 79.48s`.

Static affected-surface results:

- Ruff format check: all seven new/repair-owned files checked, passed;
- Ruff check: all affected source/tests passed with only legacy-file `E402`
  excluded;
- mypy `--follow-imports=skip`: `Success: no issues found in 6 source files`;
- Python bytecode compilation: eight affected source files passed;
- `git diff --check`: passed.

## Real evidence still required

- trusted server confirmation issuer/owner and a real issuance journey;
- authenticated Web session with machine-private credential configuration;
- registered project/session and configured real model/provider;
- one bounded real Code Agent task proving support/artifact isolation;
- real process restart, periodic reconciliation, and shutdown evidence;
- Integration Owner Gate decision and any Replacement Ledger credit.
