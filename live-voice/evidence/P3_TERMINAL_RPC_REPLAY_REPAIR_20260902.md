# Terminal Task notification RPC replay repair — 2026-09-02

Baseline: `a6ebb4d4f8cc2130e2a99a2852ef952d000a4652`; failed deployed product
source: `03adc142a5c439f5c165c70e38ea7bdba181156d`.
Current judgement belongs to [STATUS](../STATUS.md); verification policy is
root [TESTING](../../TESTING.md). This record grants no human acceptance.

## Scope checkpoint before implementation

Reopen the Gateway unary response-lifecycle boundary at Tier 3: it routes shared
AgentServer responses and must preserve cancellation and connection isolation.
This adds `jiuwenswarm/gateway/routing/agent_client.py` and its existing
`tests/unit_tests/gateway/test_agent_client.py` to the current terminal-notification
repair. The frontend-only exclusion in the preceding packet no longer describes
this child repair.

A fully parsed unary response completes its queue without creating a false
cancellation tombstone. An immediate exact-ID notification replay must reach
AgentServer again, and its new response must reach its own waiter. This includes
valid negative application responses: transport completion is independent of
application success. Timeout, malformed response, interrupted/closed stream and
old connection cleanup retain their existing residual-response isolation.
Do not bypass a real cancellation tombstone merely because a new queue exists.

Acceptance: reproduce the failure through a real localhost WebSocket and the
production receiver loop; prove consecutive successful observation and exact-ID
re-observation without delay or cached substitution. Preserve in-flight
coalescing, changed-payload rejection, cancelled-waiter ownership, disconnect/
reconnect and stream/unary isolation. Fault tests must prove zero delivery of
cancelled residual frames to a replacement waiter or unrelated request.

Exclusions: no wire/schema, server idempotency, authority resolver, Task/Tool/
Executor, frontend arbitration, timeout value, Provider/device/configuration or
remote-ref change. A controlled rebuild/restart and current browser readiness
check are authorized; physical completion hearing remains a separate observation.

## Reproduced user journey and diagnosis

Session `web_1a063a4d660_6fd7d438d6ef`, private service log
`logs/swarm-20260902-213900.log`. Times below are CEST. Credentials, raw
transcripts/audio, database contents and unrelated sessions are excluded.

- Task `task-df1d18c07219468587ddb0de444c8c12`: accepted 21:42:38.150,
  running 21:42:38.619, completed 21:42:52.673.
- Accepted/running AUDIO ACKs: 21:42:53.562 / 21:42:59.982.
- Terminal notification request
  `live-voice-p2-notification-a279fafe-3705-4740-89c8-4b7a7ae114bb`
  was sent at 21:43:08.917; AgentServer responded at 21:43:09.400 and Gateway
  published that initial result at 21:43:09.404.
- The frontend correctly replayed the exact ID at 21:43:09.441. AgentServer
  emitted its replay response at 21:43:09.493, but Gateway did not publish it.
- At 21:43:24.432, approximately 15 seconds after capture, the browser reported
  `task_audio_playout_failed` for terminal response
  `response-task-progress-b9a22f099ce03c2e19ee57140315af9a4e4e2d26`, generation 3.
  The server emitted its canonical TEXT fallback. The durable voice cursor
  remains 3 (running); TEXT reaches 5 (completed). Capture resumed at 21:43:26.

`_send_unary_once` unconditionally calls `_drain_and_remove_queue`, which
creates a two-second `_cancelled_request_ids` entry even after a valid response.
The receiver checks this entry before the new replay queue, so it drops the
replay response. The log timing fits this exact interval. The real-transport
RED/GREEN regression below establishes this causal mechanism independently.

`0c6c19033` repaired recognition settlement and visible TEXT fallback;
`03adc142a5` added missing reauthorization during same-object media startup.
Neither changed Gateway response cleanup. Their direct mocked RPC tests and
direct media-authority tests did not traverse this receiver-loop quarantine.

## Verification and scoped review

Commands from the repository root using the existing `.venv` Python:

```text
python -m pytest tests/unit_tests/gateway/test_agent_client.py -k completed_unary_replay_uses_real_websocket_receiver --no-cov -q
python -m pytest tests/unit_tests/gateway/test_agent_client.py --no-cov -q
python -m pytest tests/unit_tests/gateway tests/unit_tests/e2a --no-cov -q
python -m ruff check --select F jiuwenswarm/gateway/routing/agent_client.py tests/unit_tests/gateway/test_agent_client.py
git diff --check
```

- RED on baseline product source: both real-WebSocket consecutive-replay cases
  time out on the **second** observation, after the server emitted both replies.
  GREEN: both return observation 1 then observation 2 through the real receiver;
  both requests have identical serialized contents. A cached result cannot pass.
  Cases cover application success and application rejection. Only the test
  deadline is shortened; no product timeout or artificial replay delay changes.
- Agent client: **25 passed**. Added real-receiver fault cases cover timeout,
  malformed response and cancelled stream. Each sends a late residual before
  an unrelated valid response as an ordered barrier; the replacement queue
  remains empty, and the unrelated response is exact. Existing tests cover
  in-flight coalescing/conflict, waiter cancellation, fatal receive/send failure,
  blocked send/disconnect, reconnect admission and old queue/tombstone ownership.
- Complete Gateway/E2A: **939 passed, 2 failed, 1 skipped**. Failures are the
  unchanged Windows path assertions in
  `test_dev_init_installs_when_devecocli_missing_and_verifies_skills` (backslash
  versus slash) and `test_safe_upload_filename_strips_unsafe_parts` (backslash
  path components). Their implementation/test files are untouched; they are
  outside response lifecycle. Do not claim a cumulative passing Gate.
- Ruff undefined/unused-symbol checks and `git diff --check`: **PASS**.

Applicable D-032 matrix: `P/S/T/R/X` consecutive observation through actual
WebSocket framing/dispatch; `N/B/F` malformed, timeout and connection faults;
`C/I` exact in-flight coalescing, conflicting payload rejection, queue/token/
connection ownership and zero residual delivery; `K` Gateway/E2A compatibility
regressions. No new feature switch, schema/persistence format, authority policy
or business mutation exists in this child repair. The real localhost server is
a protocol fixture, not a live Agent, Provider, browser or human audio claim.

Complete-diff cold self-review checked that only a fully parsed unary response
sets completion, independently of application success; receiver tombstones are
never bypassed/cleared for a new queue; stream/failure quarantine, queue identity,
token cleanup and retained in-flight ownership remain intact. No introduced
scope defect remains. No callable independent local reviewer is available;
this disclosed self-review substitute grants no independent Tier-3 review PASS.

## Controlled deployment and actual product observation

Pending controlled rebuild/restart and observed results.
