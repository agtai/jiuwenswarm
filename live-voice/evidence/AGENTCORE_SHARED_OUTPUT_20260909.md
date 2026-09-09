# Shared configured-Agent output and Workflow observation

Status: verified Task 2 prerequisites in the uncommitted JiuwenSwarm batch.
This does not complete Task 2, Task 3 or real Native Realtime acceptance.
Main baseline is `66833d5ced9203ce54ffa2fcf009d4de380f62a7`;
source-installed AgentCore remains `a43444ff5326a0c1a72954126eea4f91e071d916`.
No SDK change, package reinstall, service restart or remote update occurred in
this boundary. The existing running product is not credited with these changes.

## Implemented boundary

`AgentManager.executions` consumes the existing configured JiuwenSwarm facade
once per retained Agent/session/request identity. It is an output owner and
projection, not another Agent scheduler or durable Task authority. WebSocket
streams subscribe to this owner and preserve bounded backpressure. Recent
queries cannot block a producer. Request and response copies isolate callers;
conflicting reuse of an observed request ID rejects before another execution.
The in-memory record limit is not a promise of durable deduplication.

Text disconnect closes its subscription explicitly and cancels the last
unretained producer. Retained execution survives presentation detachment.
Repeated observer cancellation does not interrupt producer cleanup a second
time. Actual Agent pins remain until the producer exits; manager shutdown
refuses to dispose Agents while their output consumers remain unsettled.
Legacy implicit sessions retain their existing default-session behavior.

Native `agent.list/get` resolve the exact already-configured session owner and
recheck activation authority. They create no Agent, tool, Task, Work or Goal.
An empty inventory means only no recently observed stream. `stream_closed`
never implies business completion. Whole events, including member AgentRef and
interaction payloads, are projected; they do not answer an interaction request.

Both projections fit 96 KiB UTF-8 and 192 KiB ASCII JSON, leaving room for the
Native operation envelope. Inventory truncation is explicit. Event results
contain a contiguous latest suffix, omitted count and sequence range. A single
oversized human-input event is omitted whole, never presented as a complete
shortened prompt. Tests pass the resulting receipt through the actual SQLite
unified journal and canonical presentation encoding.

The new scheduling seam exposed a WebSocket heartbeat cancellation race:
`wait_for` could lose cancellation when its event completed concurrently. Using
`asyncio.timeout` in the heartbeat task preserves cancellation. The mode tests
use `asyncio.wait` to require natural completion, since a `wait_for` test could
otherwise credit the extra timeout cancellation as success. Final mode calls
completed in 0.02 and 0.01 seconds.

Shared Workflow queries now request strict checkpoint reads. Actual I/O,
decoding, empty/non-object metadata, invalid/null workflow inventories and a
file replacing the session/root directory return unavailable. Missing
checkpoints remain empty without creating directories. Strict reads never
repair or write metadata. Existing restoration callers retain their default
recovery behavior.

## Focused verification and review

All Python commands used `.venv/Scripts/python.exe -m pytest`, `--no-cov`,
`-o log_cli=false` and `-q`; full coverage/suite runs were deliberately deferred.

- Native tools/contract/context, shared session Goal/Agent identity and WS
  send tests: 148 passed. This includes scope revocation, no fallback creation
  and observing the same running text producer from Native.
- Shared output, actual facade memory/history and WS send: 29 passed before
  the projection-limit extension. Actual facade tests exercise one history
  writer and identical replay; the SDK/provider adapter is isolated in these
  tests, not credited as a real model/Provider journey.
- Final shared-output tests: all 18 passed, including the dual encoding bounds,
  real journal, manager shutdown, producer failure, observer limits, backpressure,
  cancellation before entry and delayed cleanup.
- Existing AgentManager session cleanup: nine passed on the first run; the
  remaining same-key fixture used a literal POSIX path, which differs from the
  normalized production key on Windows. Loading the unchanged HEAD AgentManager
  into a fresh test process reproduced its failure. Seeding with the production
  key factory repaired the fixture; its affected rerun passed. Retirement
  production code was not changed to accommodate the test.
- Two existing text mode stream cases passed with the natural-completion oracle.
- Final strict Workflow tests plus existing WS workflow queries: 30 passed.
  Metadata identity-preservation regressions added three passing checks; the
  inherited Windows atomic-write test below remains an explicit exclusion.
- Ruff on the new services and affected new/scoped tests, Python compilation
  of changed runtime modules and `git diff --check` passed.

Independent read-only review found one shared-output P2: the initial recent
event window exceeded journal/receipt bounds. The byte-limited whole-event
projection and actual-journal tests repaired it; focused independent recheck
confirmed closure. Strict Workflow review additionally found explicit null
inventory and non-directory session parents being mistaken for absence. Both
were repaired and independently rechecked with the corresponding real-file
tests. No fixed-count review loop or full-suite rerun was used.

Inherited exclusion: `TestIdentityPreservation.test_write_is_atomic_no_empty_window`
fails with Windows `WinError 5` while its bare file reader races `os.replace`.
The identical failure was reproduced after loading `_read_metadata` and
`_write_metadata_sync` directly from HEAD `66833d5` into a fresh process, without
editing the working tree. The new read-only query does not change the writer;
this is not a passing test or a repaired production persistence claim.
The first large-prompt parameterized test also hit a test-fixture path error
because its default IDs contained the entire large input. Short case IDs fixed
that setup issue; all four associated scenarios then passed.

## Remaining accepted work

Native start/resume and complete configured Agent/Tools/Team/HITL/Core Workflow
invocation are still pending. Service retention is exercised by tests, not yet
used by a Native execution adapter. The AgentManager convenience streaming
wrapper also still calls the facade directly and must join the shared owner if
used for a common-capability entry. The Work/formal Task cutover and duplicate
runtime retirement remain Task 2–3 work. No generated output has been newly
authorized as heard history.

Source inspection for the next Goal boundary found that Web `set` currently
sends unconditional `overwrite_confirmed: true`, without observed Goal identity
or control revision. Text pause/resume also reads then controls without CAS.
The accepted next step must bind UI edit/confirmation state and text/Native
commands to the exact SDK target, preserve attach/control/consume order and
carry model/permission/history authority. Read-only capability observations
alone do not satisfy this Goal.

Task 2/3 commits, the final cumulative checks/review and real browser/Provider/
Agent/tool acceptance remain pending. The Goal stays active.

## Tested runtime source identity

SHA-256 of the runtime files in this uncommitted boundary:

- `jiuwenswarm/server/runtime/session_execution.py`: `a6f0e6debe9f88363377782d4ca1a191f9bfe23c3ea3260f8ed3ba65fba6d746`
- `jiuwenswarm/server/runtime/agent_manager.py`: `6ad9a56c91c4e27829e47a3693cdc61c57abb889896f49c13ca55a625b6f947a`
- `jiuwenswarm/server/runtime/agent_resolution.py`: `4834b6321079456861d5a3a28714f70e4f3bb7f6eb7ba779f5fd1bc7dbd3542a`
- `jiuwenswarm/server/agent_ws_server.py`: `8138b9dfbbff1db5daf13832a8e3b7dac096d133585dc6ef6f8b28a36b6a880d`
- `jiuwenswarm/server/runtime/workflow_queries.py`: `1f951ec29b1cb8ebc92f149822eea99d19f700b58dae3b96392aaab208bcb8f6`
- `jiuwenswarm/server/runtime/session/session_metadata.py`: `52fcf4d9163131ef481a8447ae6d331a4ab372d5131c484bec6bc01113b67bf5`
- `jiuwenswarm/server/runtime/agent_adapter/team_helpers.py`: `4d70c10df5b197013f1eec74448b2b9425a3524dc5c9fbe73c02ef18a7e87638`
- `jiuwenswarm/server/live_voice/native_business_router.py`: `7e18caad44cbda621945587bd26c1e265265765c5d09a672125040900a78fd0c`
- `jiuwenswarm/server/live_voice/native_business_context.py`: `2c18ea0d540dcf9240ac18b1e474d621c4e402d41993096ed2d7eae4ebaaa623`
- `jiuwenswarm/server/live_voice/native_business_tools.py`: `2458dd4e5ebd1b259346d82899b2c388931665ab15a264848f188d90066333a5`
- `jiuwenswarm/server/live_voice/native_business_contract.py`: `327a48ab0812c92614011be4ae4b8775eacd5f3055e479f39de641b29df8a325`
