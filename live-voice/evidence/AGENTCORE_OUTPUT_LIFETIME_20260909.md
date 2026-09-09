# Shared output lifetime across transport disconnect

This is a lifetime prerequisite inside the active
[unified execution Goal](../reviews/AGENTCORE_UNIFIED_EXECUTION_20260909.md).
Native invocation, model/permission/history propagation and Task 2/3 completion
remain pending. No runtime was deployed for this boundary.

## Source and behavior

- Main remains `66833d5ced9203ce54ffa2fcf009d4de380f62a7`; this adapter/transport
  work is part of the uncommitted Task 2/3 integration, not an extra Main commit.
- SDK `a3a1aee095aac7c647d9f516075c04d562a87968`:
  `feat(harness): bind admitted work to the actual output owner`.
  Parent `fc12e445348bfdb60f4a2e2e0208a97674b28111`, content tree
  `3ac2be187681a53f6773446e150a97e52cc8e050`.
- The fifth ordered patch, `agentcore-output-lifetime.patch`, reconstructs this
  exact tree from the pinned upstream and previous four patches. The real source
  installer reconstructed it in
  `.codex_tmp/agentcore-source-replay-output-lifetime-20260909`; the installed
  source check passed with editable import origin `.deps/agent-core`.
- No remote refs were updated. The SDK checkout is preserved; the original
  explicit uninstall and source install remain in effect without reinstalling
  the environment for each source-only change.

The SDK's synchronous `on_output_ready(token, acquired)` callback runs under the
existing control lock before scheduling. Goal identity/state/authority checks
precede it. A caller can reject custody of a closing reader without changing
Goal state, discarding pending user work or aborting the previous reader. A
finishing lease is rejected by hooked ordinary attachment; Goal set/resume use
their existing drain-and-revalidate handoff. Calls without a hook retain their
previous behavior.

The shared output service binds the exact SDK lease to the facade producer
through a private execution ContextVar, never a request metadata flag. A retained
command can transfer retention to that actual producer only within the same
configured Agent and session. Already-cancelling, foreign or unobserved readers
reject admission before Goal effects. A replay alone never upgrades retention.
Borrowed-stream observations identify `output_execution_id`, output lifetime and
sequence separately from the short command's receipt stream, and retain actual
event request IDs. Stream EOF does not claim business completion.

Client-disconnect commands synchronously fence unretained producers and skip a
second whole-Agent abort for service-owned output. Gateway/AgentServer connection
loss carries exact retained session exclusions through AgentManager, facade,
SessionManager, Deep adapter and existing Team stream cleanup. Other sessions
still cancel. Explicit user cancellation retains its existing capability path.
After retained output exits, service pins and output-token bindings are released;
the SDK session follows its existing idle-cache policy. This does not add an
immediate deferred-disposal scheduler or claim that every cached session is
destroyed on output EOF.

## Focused evidence

Checks used the source-installed `.venv`, `--no-cov -o log_cli=false -q`, with
separate pytest invocations for Main and SDK. Counts below describe their own
boundaries and include overlapping affected reruns, not a cumulative pass count.

- Five new SDK admission checks first failed for the missing hook. After its
  implementation, the output-admission file passed 27 cases; with the existing
  interaction regressions, 34 passed. The later finishing-attachment regression
  and finishing Goal handoff passed their two affected checks.
- Main shared output service: 18 passed. Shared-session/Goal/WebSocket boundary:
  97 passed, including four new custody/transport cases.
- Real AgentManager/facade/SessionManager/Deep child Gateway cleanup plus two
  foreign Agent/session rejection cases: 3 passed. The model output is replaced
  in these tests; SDK Goal storage, queue, lease and Deep Goal dispatch are real.
- Affected Team bulk-cancel lifecycle, Gateway disconnect, dedicated-service
  compatibility and output projection/replay checks: 28 passed. These include
  preserving a locked Team session while cancelling the unrelated session.
- The public AgentManager streaming entry now uses the same service and closes
  its observer explicitly: its cross-entry observation/cancellation test passed.
- The actual Gateway connection-finally scheduling race passed its new test.
  Superseded-generation isolation and the existing no-root-eviction disconnect
  regression passed together (2 cases); the existing replacement-waits-for-old-
  cleanup journey passed its affected case. Minimal manager fixtures now provide
  the actual shared service or its explicitly empty transport surface.
- Scoped Main Ruff and whitespace checks passed. SDK test Ruff passed; touched
  DeepAgent passed with the previously recorded inherited F841 excluded. No new
  unused-variable exception is claimed.

Independent review found an ordinary `attach_output` finishing-lease path that
skipped the hook but still ensured Goal work. It now rejects before scheduling;
the reviewer independently reran the new regression successfully. Infrastructure
review then reproduced a queued Goal acquiring output during route cleanup,
before the cancelled text observer had reached its finally block. The service
now fences unretained producers synchronously after the current-connection
generation check, before route cleanup can await. Its regression runs through
the actual connection handler and asserts outside the cleanup exception handler
that no Goal state or queue effect occurred. An old connection cannot fence a
replacement generation. The final independent review reran the actual finally
race, superseded-generation and public AgentManager stream cases: 3 passed.
Both confirmed findings are closed; no further findings remain in this bounded
review. This is not the final Task 2/3 or product-candidate review.

## Remaining work

The production Native tool schema still has no shared Agent start or Goal
set/resume operation. The retained service caller in the integration test proves
the ownership seam, not a complete Native product path. Trusted model/version,
tool permissions, per-execution history and presentation ACK must accompany that
actual dispatch. Team/HITL, Core Workflow invocation, Work/formal Task cutover,
duplicate runtime removal, Main Task 2/3 commits and final automated/real browser,
Provider, Agent and tool acceptance remain required. The Goal remains active.

## Tested runtime identities

- `jiuwenswarm/server/runtime/session_execution.py`: `99d879231f1e939c5e3b92675d5bcb136c43eb6ff03238e526287c055a45c8fc`
- `jiuwenswarm/server/runtime/agent_manager.py`: `ce94049c97d723b045dc84e32effabbdf7f6d6a12711bc95e767daaebeea1a22`
- `jiuwenswarm/server/runtime/agent_adapter/interface.py`: `19eddb1c13ead250be3cb42646866ec668f0bfe62f1105d43ee165e6cb13cbab`
- `jiuwenswarm/server/runtime/agent_adapter/interface_deep.py`: `17cda131f965939ac4c962294b7982cf552c21a68d12bff64b1300f7a0ce7b65`
- `jiuwenswarm/server/runtime/session/session_manager.py`: `bd73ddf75212cb6d91256ae6b4d016764017cfcbb19e664ff315d20f1e1a4734`
- `jiuwenswarm/server/agent_ws_server.py`: `aec8c599d83044b65f17982c05422e7bc10ffa57257a5748ac4be9cb025d6f8b`
- `jiuwenswarm/agents/harness/team/team_manager.py`: `c167f0b86215bac323ca6c0e49b86b206ad0b01a15d15ce1a7f00eaa71f41c0d`
