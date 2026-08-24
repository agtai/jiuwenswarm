# OpenJiuwen Task Presentation Cursor Adapter Implementation Packet

## Status and scope

- Date: 2026-08-25
- Capability: `OJ-G1-FACADE` / `EVT-06`, isolated presentation-to-cursor
  Adapter
- Risk: Tier 3 — an authentic product DOM or playout acknowledgement can
  advance durable AgentCore consumer state, while a forged, stale or merely
  queued presentation must advance nothing.
- AgentCore dependency: exact committed local candidate
  `db8216839562de36fa24fd6f5ce807acea5a132a`.
- LiveVoice baseline: `b0575038199b1061649154ee9f00252ccd36fa7a`.
- Mode: additive, default-off and uncomposed. It grants no cutover, migration,
  deletion or product-readiness credit.

## Intended behaviour

Add an asynchronous consumption seam to the retained
`TaskPresentationConsumptionOwner` and one isolated Adapter over
`OpenJiuwenTaskFacade`. The product owner remains the sole verifier of the
exact response generation, text DOM adoption or Runtime audio-ledger ACK. Only
after that verification may the Adapter translate the frozen AgentCore unread
page into one `advance_after_presentation_ack` call.

The Adapter binds all of the following before the product owner is allowed to
call the durable Port:

- authenticated product scope and the facade's frozen AgentCore scope mapping;
- Task, durable consumer and independent `text` or `voice` channel;
- current cursor sequence/version and frozen event head;
- acknowledged event sequence, ID and canonical payload digest;
- any canonical facade page size from one through 500, including a default
  100-event page with a larger retained backlog;
- exact product delivery tuple, `task.ack_events` command, authorization grant
  and fresh `ResolvedProductAuthority`;
- one stable `advance_id`, derived from the existing command ID.

AgentCore event and head sequences are one-based while the retained LiveVoice
presentation contract is zero-based. The mapping is explicit and lossless:
`livevoice_sequence + 1 == agentcore_sequence`, including cursor watermark and
frozen head. Event IDs and payload digests are never translated. The durable
`advance_id` is domain- and team-separated from the stable command ID; request
facts remain covered by AgentCore's immutable advance receipt, so changing
facts under the same command identity conflicts rather than creating a second
receipt.

The synchronous legacy `consume` method remains unchanged for the current
`SqliteTaskStore` route. The new `consume_async` method has the same ACK,
response-lifecycle, command and grant checks, invokes no Port while holding the
owner lock, and validates the returned canonical `ResultEnvelope`. Caller
cancellation propagates. If AgentCore commits before the response is lost, a
retry with the same delivery, command, authority and frozen unread facts must
return the durable AgentCore replay rather than advance twice.

The Adapter does not classify AgentCore events as spoken or visible progress.
`EVT-04` event-to-product projection remains a later packet. In this isolated
slice the caller supplies a product delivery already reserved from the same
frozen unread event; the Adapter proves only the delivery-to-cursor binding.
The delivery model also binds an execution/attempt, so this packet accepts only
execution-bound AgentCore events. Presentation of relation-less Task events is
left to that later projector decision.

## Owned surfaces

- Production:
  `jiuwenswarm/server/live_voice/presentation_ledger.py` — additive async
  consumption seam only.
- Production:
  `jiuwenswarm/server/live_voice/openjiuwen_task_presentation_adapter.py`.
- Unit tests:
  `tests/unit_tests/live_voice/test_openjiuwen_task_presentation_adapter.py`
  plus focused additive coverage in the existing presentation-consumption
  suite when required.
- Exact-candidate integration:
  `tests/integration/live_voice/test_openjiuwen_task_presentation_candidate.py`.
- This packet.

No registry, product composition root, progress classifier, legacy Task Store,
AgentCore schema, Agent/Tool launcher, D1/D2 Adapter or browser/runtime owner is
modified.

## Required fail-closed behaviour

The following must produce zero cursor advance and zero Agent, Tool, Task,
audio/history, file, legacy-Store or other-scope effect:

- presentation consumption before an authentic text or voice ACK;
- wrong response/generation/reservation/delivery/unit/surface or a closed
  response;
- malformed or mismatched unread page, cursor, Task, consumer, channel, head,
  event sequence, event ID or payload digest;
- wrong, expired or incomplete product authority, command, grant, capability,
  scope or Task resource;
- stale cursor version/head, changed-facts duplicate, wrong advance ID or a
  corrupt downstream decision;
- dependency absence, downstream exception or caller cancellation before the
  durable call completes.

After a cursor commit, response loss or cancellation may hide the response but
must not fabricate failure-side rollback. Exact retry uses the AgentCore
advance receipt. Text and voice remain separate durable channels. An accepted
Runtime audio ACK proves presentation only for the product owner; it is not a
Task terminal or Agent success fact.

## Tier-3 acceptance matrix

| Dimension | Required evidence |
|---|---|
| P | A real text DOM adoption and a real Runtime audio-ledger ACK each advance only their exact AgentCore channel through the async owner. |
| N | Pre-ACK, forged ACK, foreign authority, wrong page/delivery/event and malformed downstream results invoke zero cursor mutation and zero forbidden product effects. |
| B | Empty/NUL/surrogate and 255/256 identities, signed-bigint/bool cursor values, SHA-256 facts, event-page limit and malformed envelope shapes are rejected by the facade/Adapter boundary. |
| S | Response close fences later consumption; AgentCore cursor remains the sole durable position and product owner state remains ephemeral. |
| T | Delayed/duplicate ACK, stale frozen head, changed-facts retry and response-loss ordering remain truthful. |
| C | Concurrent same-command consumption yields one durable advance plus replay; different commands for one delivery retain one binding. Text and voice do not contend as one cursor. |
| R | Commit-before-return loss and reopen retry return the original AgentCore result without a second advance. |
| I | Product scope, AgentCore session/team/consumer, Task, response, generation, delivery, channel and event identities cannot cross-bind. |
| F | Default-off/uncomposed imports allocate nothing; dependency or downstream failure has no legacy fallback and never reports a presentation or cursor success. |
| K | Existing synchronous presentation consumption and its Store path remain unchanged; G1 facade/query, D1 and D2 Adapter regressions pass. |
| X | Exact clean AgentCore, public `TeamAgent.task_authority`, file-backed SQLite, real facade, real `TaskPresentationConsumptionOwner` and real cursor rows prove the owned seam. Browser DOM and physical audio are not claimed by this isolated fixture. |

## Explicit exclusions and later decisions

- No `EVT-04` mapping from generic AgentCore events to LiveVoice
  accepted/running/blocked/terminal presentation vocabulary. AgentCore lacks a
  runtime-start fact, so `execution_admitted` is not silently presented as
  running.
- No production registry/composition activation and no replacement or dual
  write of `SqliteTaskStore` cursors.
- No browser DOM automation or physical TTS/audio-device acceptance. Unit
  tests use the existing exact product ACK contracts; the candidate integration
  proves only the real durable cursor seam.
- No presentation close/tombstone in AgentCore. Response closure remains an
  ephemeral product fact and does not rewind or delete a cursor.
- No legacy cursor import, quiescence, canary, rollback or deletion.
- No Agent/Tool launch, Task mutation, result mapping, D1/D2 recovery, product
  update or new product classifier/policy.
- No PostgreSQL/MySQL service run, remote update, deployment or credential
  change.

## Closure evidence

- Final focused presentation/Adapter verification: **39 passed**.
- Exact clean AgentCore
  `db8216839562de36fa24fd6f5ce807acea5a132a`, public `TeamAgent.task_authority`
  and file-backed SQLite candidate: **1 passed**. It proves one real cursor
  commit, response loss, process-level reopen, exact receipt replay and
  independent unadvanced voice state.
- Affected facade/query/D1/D2/presentation/progress selection: **284 passed / 1
  failed**. The one failure is the `STATUS.md`-disclosed inherited P3 retry
  fixture that requests retry from a completed predecessor while current
  authority admits only a cancelled predecessor; this packet does not touch
  that policy or fixture.
- Ruff default and import-order checks, Ruff format check, Python compile and
  `git diff --check`: **PASS**.
- Independent Tier-3 read-only review: **C0 / I0 / M0 / L0**. The review first
  reproduced and closed two page-shape findings: legal 1..500 pages must not be
  forced to length 500, while `page_end > frozen head` must always fail before
  the cursor Port. The reviewer independently reran **39 focused + 1 exact
  candidate** tests and observed no remaining finding.
