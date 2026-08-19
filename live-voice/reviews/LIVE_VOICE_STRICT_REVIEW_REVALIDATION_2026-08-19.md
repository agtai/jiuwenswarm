# Live Voice strict review revalidation — 2026-08-19

> **Disposition: FAIL — 88 unique current defects remain.** All 106 IDs from
> `LIVE_VOICE_STRICT_REVIEW_2026-08-15.md` were revalidated against the exact
> current source. The active set contains **41 HIGH, 25 MEDIUM and 22 LOW**
> unique defects. This historical audit does not change `STATUS.md`, grant
> capability credit, or replace the active P3-2 acceptance packet.

## 1. Baseline, scope and method

- Requested source branch: local `hx/0812_live_voice_w3`, matching
  `agtai/hx/0812_live_voice_w3` at review start.
- Isolated review branch/worktree:
  `codex/live-voice-strict-review-20260819` in
  `D:\XGG AI\openjiuwen\jiuwenswarm-review-20260819`.
- Exact reviewed HEAD:
  `b1a6290b6ccbe5948c5700a8c6e103798160d7f1`
  (`docs(live-voice): freeze P3-2 command contracts`).
- Historical attachment baseline:
  `b7573d51917eca2c3b6070c2bbc8632da4b2a2b1`. The current source is 67 commits
  later; the delta touches 203 files with 61,034 insertions and 6,406
  deletions. Historical line numbers and dispositions were therefore not
  trusted.
- Audit universe: A1–A25, B1–B42, L1–L23, C1–C13 and D1–D3: **106/106 IDs**.
- Method: read the current production path, its owner/cleanup path and relevant
  tests; trace reachability from product entry points; distinguish bounded
  active state from anti-replay tombstones; and check proposed fixes against
  current authority, generation and fail-closed contracts.
- The attachment was treated only as a historical finding list, not as
  instructions or current implementation truth.

## 2. Executive result

### 2.1 Audit-ID disposition

| Current disposition | IDs | Count |
|---|---|---:|
| Confirmed in current source | A1–A9, A11–A15, A17–A23, A25; B1–B16, B18–B25, B27–B30, B32, B34–B42; L1–L6, L8–L22; D1–D3 | 84 |
| Partially fixed, residual confirmed | A16, B33, L7 | 3 |
| Historical rejection overturned, new unique defect | C5 | 1 |
| Historical rejection partially overturned; active part aliases B42 | C3 | 1 |
| Fixed in current source | A10, A24, B31, L23 | 4 |
| Duplicate historical ID; underlying issue remains as B13 | B17 | 1 |
| Superseded by accepted authority decision | B26 | 1 |
| Historical rejection still valid | C1, C2, C4, C6–C13 | 11 |
| **Total** |  | **106** |

There are 89 active audit IDs. C3's surviving command-ledger concern is the
same defect as B42, so the actionable total is **88 unique defects**. B17 is a
second historical ID for B13 and is not counted as active.

### 2.2 Current severity of unique active defects

| Severity | Count | Main concentration |
|---|---:|---|
| HIGH | 41 | authority/generation integrity, privacy, permanent availability exhaustion, event-loop/global-lock stalls, cancellation and teardown |
| MEDIUM | 25 | protocol parity, bounded cleanup, state monotonicity, durable validation, cross-owner races |
| LOW | 22 | dead evidence, diagnostic fidelity, bounded compatibility state and test gaps |

### 2.3 Highest-priority repair batches

1. **Privacy and authority integrity:** A21, B9, B10, B12–B14, B16, B18,
   B29, B36–B39, B41, C5, L20–L21. Fix these before reliability-only work;
   every negative path needs zero Agent/Tool/Task/history/media side effects.
2. **Unbounded lifetime state with permanent refusal:** A1, A5, A6, A9,
   A13, A15, A17, A25, B4, B11, B42. Heavy records need an owner-scoped
   release lifecycle plus a separate bounded anti-replay fence; a plain LRU is
   not safe.
3. **Cancellation, shutdown and successor ordering:** A2, A7–A8, A16,
   A19–A20, A22, B2, B6–B7, B21, B23–B24, D1–D3. Use the common pattern:
   publish a generation fence, settle every owned child in `finally`, preserve
   the business outcome, and retain cleanup truth when a total deadline expires.
4. **Responsiveness under blocking work:** A4, A11, A14, B15, B25, B27.
   CPU/SQLite/filesystem work and slow activation must not run under the event
   loop or the process-wide product lock.

## 3. Historical HIGH findings A1–A25

All unresolved A findings retain current severity HIGH.

- **A1 — confirmed, HIGH.** `streaming_speech.py:469-490,522-523,
  1028-1048,1215-1238,1597-1606` retains generation/response identities for
  the conformance instance lifetime; terminal reap removes active state but
  not the 64-entry identity ledger. The default provider at
  `openai_streaming_speech.py:879-881` and product TTS allocation at
  `dedicated_media_registration.py:2658-2687` therefore lose streaming after
  64 distinct streams for that conformance/provider owner's lifetime.
  **Change:** release heavy terminal identities by connection/session and keep
  a bounded generation tombstone; align provider and route capacities.
  **Verify:** more than 64 sequential successful streams remain usable while
  stale generation replay is rejected.

- **A2 — confirmed, HIGH.** `openai_streaming_speech.py:1236-1250` calls
  conformance cancellation before local retirement. If COMPLETED is queued but
  unconsumed, `streaming_speech.py:1141-1147,1366-1395` raises
  `SYNTHESIS_ALREADY_TERMINAL`; Provider stream/transport close and
  `_retire_synthesis` are never reached, and the route swallows the cancel
  failure at `streaming_synthesis_route.py:1785-1819`. The current active-stream
  cancel test does not exercise this race. **Change:** treat local terminal as
  an idempotent Provider stream/transport-close and retire path, preferably in
  `finally`.
  **Verify:** pause after COMPLETED publication, cancel before dequeue, then
  assert stream-not-found, closed transport and no retained queue/session.

- **A3 — confirmed, HIGH.** `batch_speech.py:751-767,2240-2262,
  2348-2383` accepts `text.strip()` as non-empty but publishes and signs the
  original whitespace-bearing text; receipt validation at `1562-1570` rejects
  it after capture identity was reserved. **Change:** canonicalize once at the
  provider boundary and use the same text for event, hash and receipt.
  **Verify:** ASCII and Unicode surrounding whitespace produce one canonical
  receipt, and exact operation replay does not invoke the Provider again.

- **A4 — confirmed, HIGH.** The pure-Python sample loop in
  `batch_speech.py:463-535` is called synchronously by async synthesis at
  `769-798`, blocking barge-in, cancellation and heartbeats for large PCM
  results. **Change:** move resampling to `asyncio.to_thread` or a GIL-releasing
  bounded implementation. **Verify:** maximum supported audio preserves bytes
  while a concurrent heartbeat/cancel stays inside its latency budget.

- **A5 — confirmed, HIGH.** `ConversationRuntime` constructs a default
  128-entry `TurnCommitLedger` at `conversation_runtime.py:132-157`; although
  `live_voice_contract_v2.py:2604-2618` now exposes `release_origin`, the runtime
  never calls it, while `agent_conversation_runtime.py:502-512,574` permits 256
  requests.
  **Change:** tie capacity to the runtime contract and release heavy commit
  state when exact response authority ends, retaining a compact replay fence.
  **Verify:** at least 129 sequential turns succeed; released old commits still
  cannot replay.

- **A6 — confirmed, HIGH.** `agent_conversation_runtime.py:184-242,
  347-363` never releases `_critical_keys`, and publication exceptions escape
  the sole bridge consumer at `2640-2652,2793-2799`. One duplicate or reserve
  exhaustion can kill all later Agent/progress consumption. **Change:** split
  queue capacity from bounded replay identity and supervise publication
  failures without terminating the long-lived consumer. **Verify:** an injected
  critical publish violation yields an explicit failure and the next request is
  still delivered with zero forbidden effects.

- **A7 — confirmed, HIGH.** Shutdown at
  `agent_conversation_runtime.py:2801-2878` wraps bridge, consumer, harness,
  conversation runtime and notification cleanup in one `try`; the first error
  skips every later owner. **Change:** run ordered, independently guarded
  teardown phases and aggregate/preserve errors. **Verify:** inject failure in
  each phase and assert every later owner is called once, children are settled
  and a second close converges.

- **A8 — confirmed, HIGH.** `jiuwenswarm_round_harness.py:776-864` can set a
  correct completed/cancelled business outcome and then overwrite it with
  FAILED when `aclose()` throws. **Change:** record cleanup disposition
  separately and only create FAILED when no business outcome exists.
  **Verify:** completed+close-failure and cancelled+close-failure preserve the
  terminal truth; unknown+close-failure becomes failed without orphan tasks.

- **A9 — confirmed, HIGH.** `progress_notification_arbiter.py:300-322,
  890-901,1449-1512` ACKs only remove pending delivery; work, source,
  observation, stream and decision identities remain for the process lifetime
  and permanently exhaust capacity. **Change:** add terminal+ACK
  `release_work/release_scope`, retaining a bounded digest tombstone.
  **Verify:** sequential terminal+ACK traffic beyond every cap continues, old
  event replay fails and another scope is unaffected.

- **A10 — fixed.** `task_store.py:4098-4152,5189-5229` now suppresses
  terminal/stale claimed outbox rows on explicit release and expired-lease
  reset rather than returning them to pending. Current tests cover terminal
  release, lost reconciliation and successor retry at
  `tests/unit_tests/live_voice/test_persistent_task_core.py:1334-1384,
  1568-1608`. The focused current-source test run in this review passed.

- **A11 — confirmed, HIGH.** Async `drain_outbox_once` and `reconcile` in
  `persistent_task_core.py:648-890` call synchronous SQLite store methods on
  the event-loop thread. **Change:** run individual store operations through
  the existing blocking runner/`to_thread`; keep async executor calls on the
  owning loop. **Verify:** an injected 200 ms store stall cannot delay
  heartbeat/barge control, and SQLite serialization/restart behavior remains
  correct.

- **A12 — confirmed, HIGH.** `project_code_executor.py:3192-3209` observes
  persisted `cancel_requested` and emits cancel acknowledged but finishes as
  INTERRUPTED, whereas the adjacent cancellation path at `3280-3300` uses
  CANCELLED. **Change:** derive an explicit user-cancel cause; persisted cancel
  and cancel acknowledgement must settle CANCELLED, reserving INTERRUPTED for
  shutdown/lost ownership. **Verify:** barrier the journal write and in-memory
  signal and assert one CANCELLED terminal with correct retry semantics.

- **A13 — confirmed, HIGH.** Accepted commits enter the registry at
  `product_composition_registry.py:2470-2479`. Capacity eviction at
  `2553-2573` removes a completed P2 operation, but `1813-1818` retires only
  unknown, not accepted, commits. `handle_p2_close` at `5861-5864` and active-
  route shutdown at `8786-8788` call the helper at `7158-7170`, which also
  leaves accepted commits. Repeating successful task-origin submit then closing
  the route without P3 create fills 128 accepted entries for the running
  registry lifetime; only `stop` at `8856-8862` releases all. **Change:** give
  abandoned closed-route origins a bounded late-create grace, then release
  heavy state and retain a compact stale/replay fence. **Verify:** 128 abandoned
  routes do not block a new submit; one late create works within grace and
  retired replay is stable. Existing eviction tests do not cover this sequence.

- **A14 — confirmed, HIGH.** `handle_p3_query` holds the registry-wide lock
  across adapter/root/SQLite awaits at
  `product_composition_registry.py:6524-6546,7619-7784`. **Change:** reserve a
  generation-fenced in-flight token under lock, perform slow authority/store
  work outside it, then validate and commit under lock; stop should wait on an
  explicit in-flight condition. **Verify:** while one query is blocked, another
  session's barge-in completes promptly and stop still waits/cleans correctly.

- **A15 — confirmed, HIGH.** `_leases` in
  `product_p2_interaction_adapter.py:1154,1199-1203` has no cap or terminal
  callback; only a higher generation of the same key removes a closed lease.
  **Change:** delete heavy closed leases on terminal notification and keep a
  separate bounded generation tombstone. **Verify:** many distinct closed
  interactions remain bounded while stale generation replay is rejected.

- **A16 — partially fixed, residual HIGH.** Attach and receive/boundary sends
  now use cleanup handling (`dedicated_media_route.py:938-960,1021-1143`), but
  post-parse detach sends and binary ACK at `1153,1157,1164,1168` lie outside
  it; cancellation closes the session but can leave socket, child tasks and the
  cleanup reservation. **Change:** put the entire post-reservation leaf in one
  idempotent outer `try/finally`. **Verify:** cancel separately while each of
  four sends is blocked; reservation usage returns to zero, children settle or
  are explicitly retained, and the socket closes once.

- **A17 — confirmed, HIGH.** `streaming_synthesis_route.py:510-560,
  716-763,1850-1867` retains 256 binding tombstones forever and throws raw
  capacity failure, bypassing the normal batch-eligible fallback. **Change:**
  implement bounded identity retirement and, independently, convert capacity
  exhaustion to a typed batch-eligible result. **Verify:** beyond 256 streams
  the product falls back without handler failure while stale bindings remain
  fenced. This is a separate second limit from A1.

- **A18 — confirmed, HIGH.** Schedule create/run at
  `agent_ws_server.py:9492-9540,9587-9624` uses lazy `agent.get_instance()`;
  the cold-root value can be `None` before persistence/trigger. **Change:** use
  `await agent.ensure_instance()` and validate it before any schedule/task
  effect. **Verify:** cold create/run singleflight succeeds; initialization
  failure creates no schedule or task.

- **A19 — confirmed, HIGH.** Connection replacement at
  `agent_ws_server.py:1615-1637` holds the lifecycle lock while waiting without
  a bound for `previous_done`; the old handler does not set it from an
  unconditional outer `finally`. **Change:** always signal completion and use a
  bounded, generation-fenced takeover with retained old cleanup. **Verify:** a
  cancelled/non-cooperative old cleanup cannot prevent timely new ACK or let
  the old generation erase new state.

- **A20 — confirmed, HIGH.** Gateway shutdown at `app_gateway.py:2866-3013`
  is linear; an exception from `web_channel.stop()` skips all other channels,
  scheduler, heartbeat, forwarding, client and restart cleanup. **Change:** use
  independently guarded ordered phases, attempt every owner and aggregate
  errors; restart only after the required safe boundary. **Verify:** inject Web
  stop failure and assert all later owners run once and the original error is
  visible.

- **A21 — confirmed, HIGH.** `agent_client.py:39,54-80,671-674,743-746`
  redacts only `auth_token` and logs complete unary/stream payloads at INFO,
  including Live Voice text/transcript and identifiers. **Change:** reuse the
  common recursive privacy projector or log only an allowlisted method/request
  summary. **Verify:** nested, case/format-varied transcript, audio and
  credential markers never appear at INFO/DEBUG and input data is unchanged.

- **A22 — confirmed, HIGH.** `productP1VoiceRoute.ts:915-938,1506-1565,
  1845-1850` clears pending playout before rejecting failure; catch/final
  cleanup then loses the dedicated downlink route and cannot issue local close.
  **Change:** move exact pending ownership to settling, or close its downlink
  before clearing, while preserving the device/render failure reason.
  **Verify:** streaming and batch downlink playback failures close socket/leaf
  and revoke the exact gateway lease once.

- **A23 — confirmed, HIGH.** `productWebActivation.ts:938-952,994-1009,
  1074-1086,1140-1155` inserts pending submit/barge/presentation entries before
  durable freeze/checkpoint. UTF-8 byte validation or journal failure leaves a
  result-less ghost that blocks retry. **Change:** freeze and checkpoint before
  retention, or delete only the newly inserted entry in a guarded rollback.
  **Verify:** multibyte over-limit and checkpoint failures leave no pending
  entry/network effect and a subsequent valid operation succeeds.

- **A24 — fixed.** `productWebActivation.ts:902-935,1184-1198,
  1306-1314` now reserves media start atomically and close cancels/awaits it
  before successor activation. The panel uses that owner and suppresses rollover
  during P1 start/capture/recognize/play at
  `LiveVoiceIntegratedRoutePanel.tsx:3120-3123,4008-4020`. Current tests cover
  close-before-successor and session replacement ownership at
  `frontend/tests/productWebActivation.test.mjs:445-493` and
  `frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs:4842-4946`.

- **A25 — confirmed, HIGH.** `p3_confirmation.py:27-28,545-650,725-786`
  counts every SQLite row toward 4096 and only marks consumption; consumed and
  expired confirmations are never deleted, so destructive confirmation becomes
  permanently unavailable across restart. **Change:** transactionally purge
  consumed/expired heavy rows before admission, retaining only the replay data
  the policy actually requires. **Verify:** consumed and expired rows reclaim
  capacity, live rows do not, and restart/replay behavior stays explicit.

## 4. Historical MEDIUM findings B1–B42

- **B1 — confirmed, LOW.** The five zero-authority counters asserted by
  `test_streaming_speech.py:192-203` remain default-only fields from
  `streaming_speech.py:411-426`; `_snapshot_unlocked` at `1244-1271` never
  updates them. **Change:** remove the dead counters and use a complete public
  callable allowlist, or wire them to real observable effects. **Verify:** a
  deliberately added business mutation makes the zero-effect helper fail.

- **B2 — confirmed, MEDIUM.** Recognition has the same queued-terminal race as
  A2: `openai_streaming_speech.py:1153-1175` calls conformance before local
  retire, so an unconsumed FINAL raises terminal and retains the `_recognition`
  session and queued transcript; the completed path has already closed the
  socket at `1549`. **Change:** make local terminal cancellation perform
  idempotent session/queue retirement and transport cleanup in `finally`.
  **Verify:** publish FINAL, do not dequeue, cancel, then assert map/session and
  queued transcript release, idempotent transport cleanup and zero business
  effects.

- **B3 — confirmed, MEDIUM.** The event timeout at
  `openai_streaming_speech.py:1736-1749` includes parsing and bounded queue
  publication; consumer backpressure can be misreported as provider timeout
  before `_put_bounded`'s own budget at `1870-1896`. **Change:** apply provider
  timeout only to `anext(iterator)`. **Verify:** a full queue with a shorter
  event timeout reports `SPEECH_EVENT_QUEUE_EXHAUSTED`, not provider timeout.

- **B4 — confirmed, MEDIUM.** `_critical_keys` at
  `agent_conversation_runtime.py:192,214-235,284,347-363` is both a uniqueness
  ledger and capacity counter and never releases after drain/discard; progress
  has no independent terminal quota. **Change:** size capacity by queued items
  and keep bounded replay tombstones separately. **Verify:** drain/discard past
  capacity remains usable, duplicates fail, and progress cannot starve terminal
  or presentation notification.

- **B5 — confirmed, MEDIUM.** Claim/ACK first calls
  `_prune_invalid_output_effects`; `agent_conversation_runtime.py:3090-3124`
  marks even acknowledged claims superseded after presentation state changes.
  **Change:** acknowledged claims must remain replayable/settled, or use a
  distinct stale-but-acknowledged state. **Verify:** both presentation/effect
  ACK orders and exact ACK replay retain the same effect result.

- **B6 — confirmed, HIGH.** Harness terminal publication waits for `aclose`,
  and `_await_retained_cleanup` at `jiuwenswarm_round_harness.py:844-855,
  887-896` repeats five-second slices forever. **Change:** set a total cleanup
  deadline, transfer unfinished work to a retained-cleanup owner and publish
  accurate pending/unknown cleanup truth. **Verify:** a never-returning
  `aclose` cannot block terminal/close indefinitely or create forbidden effects.

- **B7 — confirmed, HIGH.** `critical_token_safety.py:1001-1029` releases an
  old commit and unconditionally pops the interaction's active clarification
  and authorization indexes, even if a successor commit owns them. **Change:**
  pop only when the current mapped ID equals the exact released ID.
  **Verify:** replace an active binding, release the old commit, then prove the
  successor still authorizes while the old commit cannot dispatch.

- **B8 — confirmed, MEDIUM.** `task_progress_return.py:947-1005` drains one
  voice decision by scope rather than exact work; one bridge can consume another
  task's result and fail itself. **Change:** filter arbiter drain by `work_ref`,
  or requeue/ignore foreign decisions without poisoning either bridge.
  **Verify:** two same-scope voice tasks with interleaved progress consume only
  their own decisions.

- **B9 — confirmed, HIGH.** `voice_task_bridge.py:1039-1070` validates only the
  first truthy instruction/token/task source. A resolver can return instruction
  plus confirmation token with no operation and bypass token span validation.
  **Change:** validate every populated field independently and make
  instruction/token mutually exclusive. **Verify:** malicious mixed fields
  fail with zero Task, Tool and confirmation effects.

- **B10 — confirmed, HIGH.** `StaticBearerAuthenticator` at
  `p3_authenticated_composition.py:221-238` permits non-ASCII configuration or
  candidates, then `hmac.compare_digest(str,str)` raises `TypeError` rather
  than a typed authentication failure. **Change:** reject non-ASCII config at
  startup and candidate input as unauthenticated, or compare normalized bytes.
  **Verify:** both cases fail closed before store/executor/authority effects.

- **B11 — confirmed, MEDIUM.** `_retained_worktree_cleanups` in
  `project_code_executor.py:2403,2556,2574,2625,3365` is unbounded and excluded
  from dispatch capacity; only close retries it. **Change:** count running plus
  retained cleanup, add safe bounded re-drive and never delete when ownership
  is unknown. **Verify:** retained capacity rejects before creating worktree or
  Agent and recovers after the underlying cleanup succeeds.

- **B12 — confirmed, HIGH.** Progress generation admission in
  `product_composition_registry.py:681,1077-1107,7971` evicts the entire key at
  capacity and keeps no generation high-water, allowing an old generation to
  activate again. **Change:** retain an owner-scoped monotonic fence independent
  of heavy route state. **Verify:** fill/evict/replay an old generation and
  assert exact stale rejection with zero subscription/output effects.

- **B13 — confirmed, HIGH.** Higher-generation P2 replacement at
  `product_composition_registry.py:1872,2008-2009` pops the closed route and
  retains a tombstone but omits the voice-origin drop and exact critical-token
  release performed by normal close at `5862-5872,8787-8796`. **Change:** run
  the same exact, generation-safe cleanup before publishing a successor; pair
  with B7's conditional index release. **Verify:** old origin/token cannot act
  after replacement and the successor remains intact.

- **B14 — confirmed, HIGH.** Critical gate/generation entries in
  `product_composition_registry.py:663-664,2869,3103` survive a gate-approved
  submit that later fails; failure cleanup at `2534+` handles pending/unknown
  only. **Change:** release both exact maps and token gate on definite failure,
  add capacity and stop-time assertions. **Verify:** force post-gate origin
  admission failure and assert no retained entry and no release of a successor.

- **B15 — confirmed, HIGH.** P2 activation holds the registry-wide lock from
  `product_composition_registry.py:1938` across authority, old lease close and
  slow Agent/root allocation, blocking unrelated barge/close/poll at
  `5557-5608`. **Change:** reserve under lock, do slow work outside, then
  generation-check before commit, or use keyed locks. **Verify:** blocked
  session A activation cannot delay session B control, and revoked late A
  cannot publish.

- **B16 — confirmed, HIGH.** `_p3_control_manifest` at
  `product_composition_registry.py:5896` fabricates formal authority/runtime
  facts and is attached to unauthenticated, invalid and missing-record failures
  via `_intent_rejected_result`. **Change:** construct the manifest solely from
  facts actually observed; unobserved owners must be unavailable. **Verify:**
  authentication, feature, invalid input and absent-record failures never claim
  trusted authority, open lease or observed runtime.

- **B17 — duplicate alias, not a second defect.** It names the same replacement
  cleanup omission as B13. Preserve this ID for traceability; implement and
  verify only the exact B13 fix.

- **B18 — confirmed, HIGH.** `product_p2_interaction_adapter.py:1200,
  1307,1360-1365,1451` deletes a closed old lease before successor allocation;
  allocation failure loses the only generation high-water and permits gen1
  replay. **Change:** keep generation fence independent of the lease, or use a
  two-phase replacement that records attempted generation first. **Verify:**
  gen1 closed, gen2 allocation failure, gen1 replay must reject without runtime
  creation.

- **B19 — confirmed, MEDIUM.** `product_p3_text_adapter.py:94-130,466-502,
  913-943,965-970` classifies `AUTHORITY_HANDOFF_UNAVAILABLE` as both cleanup-
  forbidden and inactive, but a prepared voice source has already created
  cleanup; constructing that inactive result can raise `ValueError`.
  **Change:** permit/settle optional cleanup for this reason or propagate the
  correct handoff policy. **Verify:** prepared voice plus disabled handoff
  returns typed inactive and closes without sink effects.

- **B20 — confirmed, MEDIUM.** `alpha_benchmark.py:375-399` computes latency
  percentiles and sample count from all selected samples before separating
  failures, allowing fast failures to make a target pass. **Change:** compute
  latency only from successes and report total/failure counts separately.
  **Verify:** slow successes plus fast allowed failures cannot pass; all-failed
  input has no valid success percentile.

- **B21 — confirmed, HIGH.** `streaming_recognition_result` waits up to 36
  seconds in `dedicated_media_registration.py:146,1793-1862`; the Web socket
  dispatch path awaits handlers serially, blocking same-connection close/cancel
  and receipts. **Change:** return pending/use asynchronous push, or introduce
  bounded concurrent dispatch with required method ordering. **Verify:** a
  blocked result request cannot delay later same-connection cancel/close and a
  late result is fenced.

- **B22 — confirmed, MEDIUM.** Pre-open streaming audio at
  `dedicated_media_registration.py:141,573,1612-1630` is capped only by 800
  frames; each frame is a potentially huge Python float tuple. **Change:** add
  a sample/byte resident budget or store packed PCM16. **Verify:** oversized
  frames hit the byte bound before count and abort/clear exactly once.

- **B23 — confirmed, HIGH.** `streaming_speech_route.py:74-77,1077-1101`
  allows enough active streams for event/send tasks to consume the whole common
  provider pool; fallback cancellation uses that same exhausted pool while the
  cleanup reserve is close-only. **Change:** send cancel through a reserved
  cleanup pool or size for `2*active + cleanup reserve`. **Verify:** saturated
  event/send work still invokes cancellation and retires the stream.

- **B24 — confirmed, HIGH.** `streaming_synthesis_route.py:552-555,712-764,
  1128-1139,1251,1338-1347` stores the caller's WebSocket/RPC task as selection
  or opening work; close/successor directly cancels it and can kill the whole
  connection request task. **Change:** cancel only tasks created by the owner;
  callers observe supersession through a future/event. **Verify:** slow select
  or open racing close leaves the connection task alive for a later RPC.

- **B25 — confirmed, MEDIUM.** `session_history.py:18,558-590` uses one
  process-wide file lock and scans the complete JSON/JSONL history for every
  idempotent append. It is offloaded from asyncio but remains O(history) and
  cross-session serialized. **Change:** use per-session locks plus a durable
  record-ID index/SQLite while preserving duplicate/conflict semantics.
  **Verify:** large histories do not full-scan, two sessions do not block each
  other, duplicate returns false and conflicting payload fails.

- **B26 — no longer applicable.** Current `scheduler.py:490-514` deliberately
  terminal-fails restarted pending recurring tasks that lack their original
  execution context. D-028 (`decisions/DECISIONS.md:277-284`) forbids borrowing
  a mutable new Agent, and current tests enforce fail-closed behavior. The old
  recommendation to return them to pending would violate current authority.

- **B27 — confirmed, MEDIUM.** `_snapshot_target_tree` at
  `scheduler.py:68-120` now runs in a thread but reads every tracked/untracked
  file twice per execution without file-count, single-file or total-byte caps.
  **Change:** prefer Git blob/index identity plus bounded worktree delta, or
  reject over explicit limits before Agent start. **Verify:** huge files/many
  untracked files fail closed while ordinary changes remain detectable.

- **B28 — confirmed, LOW.** `audioPort.ts:279-288` still returns a hard-coded
  zero `businessCancelCount`, and tests merely assert zero; the layer has no
  business-cancel API, so the metric is not evidence. **Change:** remove/rename
  the pseudo-measurement and observe actual response/round/task cancel RPCs at
  orchestration boundaries. **Verify:** local stop leaves all real business
  cancel spies at zero.

- **B29 — confirmed, MEDIUM.** Identity registry errors disagree across
  languages: TS emits CONFLICT/NOT_FOUND at `liveVoiceContractV2.ts:638,657`,
  while Python defaults to INVALID_ARGUMENT at
  `live_voice_contract_v2.py:1067-1069,1091-1094`. **Change:** freeze a shared
  reason-to-code map or specify Python codes explicitly. **Verify:** identical
  vectors match both reason and code in TS and Python.

- **B30 — confirmed, MEDIUM.** `browserAudioDeviceSelection.ts:195+,
  350-356` queues device changes only while refreshing, dropping changes during
  load/reload; the initial listener is also attached after enumeration.
  **Change:** queue changes during loading, attach earlier or enumerate again,
  and drain queued refresh after ready. **Verify:** unplug during delayed load
  updates the final list and invalidates old device authority.

- **B31 — fixed.** `frontend/package.json:32,36` now defines strict build and
  execution scripts for browser gateway media and speech adapter tests, so the
  four historical test files have callable repository scripts. Keep invoking
  both scripts in the applicable validation/CI plan; they are not included by
  the integrated Web script at `package.json:44`.

- **B32 — confirmed, MEDIUM.** On barge, `productP1VoiceRoute.ts:809,
  823-827,906,915-919,942-964,1085` retains old media receipt authority and
  returns without the normal revoke; only rotation/global close cleans it.
  **Change:** barge settlement must revoke the exact receipt authority
  idempotently, retaining retry truth on failure. **Verify:** repeated barge
  without owner close keeps retained state bounded, closes every old subject
  and never revokes the new capture.

- **B33 — partially fixed, residual LOW.** New behavioral tests at
  `productP1VoiceRoute.test.mjs:4590-4636` now exercise server speech-start and
  zero Task mutation, replacing part of the old source-string-only evidence.
  They still do not assert no playout receipt, actual downlink close or complete
  old media-subject release, so B32 can escape. **Change/verify:** extend the
  behavior test with receipt, socket state and exact subject-close assertions;
  remove reliance on the remaining string-order test.

- **B34 — confirmed, MEDIUM.** `productWebActivation.ts:126-127,167-177,
  359-361` combines a 100,000-character field contract with a 131,072-byte
  durable envelope; the server also accepts 100,000 characters. Multibyte text
  can pass product validation and fail only at durability. **Change:** freeze
  one UTF-8 byte measure with envelope overhead across client/server.
  **Verify:** ASCII, three-byte Chinese and escaped JSON boundaries have the
  same acceptance set on both sides.

- **B35 — confirmed, MEDIUM.** `productTextProgress.ts:359-385,445-474`
  retries every error forever at a fixed delay; attempts are observational only.
  **Change:** terminalize definitive errors and use bounded exponential retry
  for unknown transport loss with explicit reconnect re-drive. **Verify:** a
  permanent typed error sends finitely; lost response retries the identical ACK
  and succeeds.

- **B36 — confirmed, HIGH.** `formalTaskControlLeaf.ts:339-344,525-583`
  adopts task.get/status directly without attempt, terminal/outcome or event
  head monotonicity and resets known event sequence to null. **Change:** reject
  attempt/head rollback, terminal resurrection and outcome change while
  retaining the cursor. **Verify:** after terminal events, stale get/status is
  rejected and snapshot remains unchanged.

- **B37 — confirmed, HIGH.** Session replacement at
  `LiveVoiceIntegratedRoutePanel.tsx:1287-1288,2399-2436,3257-3291` does not
  clear P3 task name/instruction, so an old voice draft can be submitted in the
  new session. **Change:** clear every P3 draft/confirmation binding atomically
  with session replacement. **Verify:** enter a draft, switch session, assert
  empty fields and zero Task/confirmation request on stale submit.

- **B38 — confirmed, MEDIUM.** `issueP3MutationConfirmation` commits a one-shot
  voice receipt at `LiveVoiceIntegratedRoutePanel.tsx:4632+,4689` before
  `buildP3Mutation` at `4711`; an empty draft returns null silently after
  consumption. **Change:** before commit, validate draft, operation and owner
  eligibility only; then commit the exact voice origin and construct the
  mutation from that binding. An alternative early builder must accept the
  pending exact voice binding explicitly, rather than silently downgrading it
  to structured origin. Surface any post-commit race as explicit failed state.
  **Verify:** an empty draft never calls commit, and a later race neither hides
  nor duplicates mutation or changes its voice origin.

- **B39 — confirmed, HIGH.** Retry eligibility polling at
  `LiveVoiceIntegratedRoutePanel.tsx:4423-4565` creates/adopts a new progress
  route object every poll even for the same task; cleanup/reactivation repeats
  and missing origin input downgrades an existing voice origin to null.
  **Change:** replace only on actual identity change and preserve verified
  origin absent explicit handoff. **Verify:** many nonterminal polls activate
  once, keep owner/origin and lose no progress event.

- **B40 — confirmed, LOW.** The mounted session-replacement test at
  `liveVoiceIntegratedRoutePanelMounted.test.mjs:2723-2760` is disconnected and
  checks only render/unmount; it creates no owners or close/disconnect spies.
  **Change:** build connected P1/P2/P3 owners and assert exact teardown plus all
  input/draft resets. **Verify:** the test must directly catch B37.

- **B41 — confirmed, HIGH.** `devWsTrafficPrivacy.ts:17-18,48-62` redacts
  final/raw text but not real `display_text` or `spoken_text`; current tests omit
  both. **Change:** prefer an allowlisted log schema, at minimum add compact and
  structured forms of those keys. **Verify:** real recognition alternatives and
  render plans never persist original text, including malformed JSON paths.

- **B42 — confirmed, HIGH.** Six barge/cancel fingerprint/result/error maps in
  `conversation_runtime_loop.py:180-188,398-434,508-555,741-807` have no lifetime
  capacity and retain raw Exception objects/tracebacks. Queue `control_capacity`
  does not bound completed commands. **Change:** add a bounded fail-closed replay
  ledger and persist only stable error code/reason/message. **Verify:** more than
  capacity successful and failed IDs keep memory bounded; evicted old IDs cannot
  execute again. C3's surviving concern is this same defect.

## 5. Historical LOW findings L1–L23

- **L1 — confirmed, LOW.** `streaming_speech.py:923-975` checks global identity
  capacity before `_make_response_capacity`, and calls that helper only for a
  new response after the check; the eviction helper at `1608-1629` remains
  unreachable. **Change:** delete it and document fail-closed behavior, or
  redesign active/generation/tombstone admission together. **Verify:** cap
  boundary and stale-ID replay have no eviction side effect.

- **L2 — confirmed, LOW.** `speech_ports.py:398-447` applies ResponseFence only
  to CHUNK; a late COMPLETED from a replaced response is accepted. CANCELLED may
  reasonably retain cleanup exemption. **Change:** fence CHUNK and COMPLETED,
  leave only explicit cancellation cleanup exempt. **Verify:** stale complete
  rejects and stale cancel still settles cleanup.

- **L3 — confirmed, LOW.** Recognition failure at
  `openai_streaming_speech.py:1369-1424` closes the socket on the error branch
  and then again unconditionally. **Change:** converge on one idempotent finally
  owner. **Verify:** failures before and after ready invoke the underlying close
  exactly once.

- **L4 — confirmed, LOW.** Batch recognition signs the voice receipt at
  `batch_speech.py:2382-2384` before worker terminal/deadline admission at
  `2140-2162`; a boundary timeout fences the result but leaves the receipt and
  its capacity. **Change:** issue only after terminal admission, or revoke by
  operation on timeout/cancel. **Verify:** controlled boundary timeout leaves no
  claimable receipt or ledger residue.

- **L5 — confirmed, LOW.** `_cancel_results` at
  `jiuwenswarm_round_harness.py:378,656-732` stores every new successful or
  failed cancel command forever, independent of bounded round reservations.
  **Change:** add a bounded fail-closed cancel replay ledger. **Verify:** unique
  rejected commands hit a stable cap and exact replay/conflict remains correct.

- **L6 — confirmed, LOW.** In-memory `task_core.py:306-339,559-593` terminalizes
  an attempt and task under two separate lock acquisitions, exposing terminal
  attempt plus nonterminal task and a cancel interleave. Production uses it only
  in a fake vertical today. **Change:** perform both mutations in one locked
  helper. **Verify:** barriered threads never observe the mixed snapshot or
  insert cancel between the writes.

- **L7 — partially fixed, residual MEDIUM.** `_run` now closes its source in
  `task_progress_return.py:1062-1115`, but `close()` at `898-916` returns early
  for externally induced FAILED; `drain_voice` can fail while the worker remains
  blocked reading source. **Change:** early-return only when source and worker
  are settled; otherwise run idempotent close. **Verify:** arbiter/emit failure
  during blocked read still closes source and terminates polling.

- **L8 — confirmed, LOW.** The Chinese quoted-name regex at
  `voice_task_bridge.py:257,571-577` accepts whitespace-only content, chooses it
  as truthy, then strips to an empty invalid task name instead of defaulting.
  **Change:** normalize before fallback or require a non-whitespace capture.
  **Verify:** ASCII space, NBSP and a valid Chinese name.

- **L9 — confirmed, LOW.** `ProductSegmentActivationError.reason` is stored at
  `product_composition_root.py:58-76` but discarded by activation mapping at
  `287-371`. **Change:** remove the dead parameter, or constrain it to a stable
  safe token and propagate it separately from exception text. **Verify:** safe
  reason propagation, private-string redaction and rollback-error precedence.

- **L10 — confirmed, LOW.** Server `RouteDescriptor.contract_version` at
  `observability.py:636-639,982-1031` accepts unbounded arbitrary optional text,
  unlike token-validated owner/provider. **Change:** require known versions or
  a bounded stable token/null. **Verify:** blank, private marker and overlong
  inputs never reach the sink.

- **L11 — confirmed, LOW.** The hard-unavailable zero-effect test at
  `test_product_p3_text_adapter.py:667-690` never supplies the prepared-source
  factory and misses the actual handoff path at
  `product_p3_text_adapter.py:916-943`. **Change/verify:** inject the factory and
  cover usable and invalid/unusable handoff, exact detach and zero sink effect.

- **L12 — confirmed, LOW.** One `streaming_observation_emitted` bit at
  `dedicated_media_registration.py:578,1555-1561,1602-1608,1913-1916,
  1959-1985` lets an early EOT/speech-start failure suppress later recognition
  success and latency. **Change:** use separate terminal-recognition and
  degradation slots. **Verify:** EOT failure followed by recognition success
  records both the degradation and one accurate terminal latency.

- **L13 — confirmed, LOW.** Transform failure in `speech_rpc.py:90-122` spreads
  the raw result into a public failure response; internal underscore fields such
  as `_streaming_degradation_reason` bypass the normal strip path. **Change:**
  build a closed public error envelope, never spread the original. **Verify:**
  forced transform failure exposes no internal key and preserves stable error.

- **L14 — confirmed, LOW.**
  `jiuwenswarm/agents/harness/common/auto_harness/service.py:3314,3492` still
  contains mojibake in user-visible scheduling errors. **Change:** replace both
  strings with the exact UTF-8 text `调度任务缺少服务端所有者范围`.
  **Verify:** exact error code and exact Chinese string at both entries.

- **L15 — confirmed, LOW.** TS `requiredText` uses JavaScript `trim()` at
  `liveVoiceContractV2.ts:103-107`; Python uses `strip()` at
  `live_voice_contract_v2.py:288-293`, with different Unicode whitespace sets.
  **Change:** freeze a contract-owned whitespace predicate/table. **Verify:** a
  shared corpus including FEFF, NEL, NBSP and narrow space matches both sides.

- **L16 — confirmed, LOW.** TS `parseWorkProgressSource` at
  `liveVoiceContractV2.ts:1062-1075` performs authority comparison before a
  kind allowlist, unlike Python at `live_voice_contract_v2.py:1699-1708`.
  **Change:** validate `round/task/attempt` first. **Verify:** illegal kind gets
  identical reason/code and zero registry mutation in both languages.

- **L17 — confirmed, LOW.** Shared malformed-input reasons still diverge:
  `INVALID_OBJECT_KEY`/`INVALID_JSON_KEY`, `INVALID_NUMBER`/
  `NON_FINITE_NUMBER`, and capability duplicate variants at
  `liveVoiceContractV2.ts:205,286,1402,1410` versus
  `live_voice_contract_v2.py:408,459,2244,2259`. **Change:** generate/freeze a
  common reason matrix. **Verify:** one JSON corpus drives both implementations.

- **L18 — confirmed, LOW.** Compatibility fallback telemetry routes in
  `integratedP1Route.ts:52` and `browserSpeechSynthesisAdapter.ts:88,116,143`
  retain an unbounded route list/seen-response set. **Change:** use a bounded
  telemetry ring; for response replay, rotate by adapter/session or fail closed
  at a cap rather than unsafe eviction. **Verify:** capacity and old-ID replay.

- **L19 — confirmed, MEDIUM.** `productP1VoiceRoute.ts:775-940` does not reject
  `playAgentText` reentry while already playing; the second call advances
  generation and overwrites pending ownership. **Change:** reject when playing,
  pending or settling before generation mutation. **Verify:** overlapping calls
  make the second fail synchronously, the first settles and no extra synth,
  downlink, audio or history effect occurs.

- **L20 — confirmed, MEDIUM.** `formalTaskIntentRoute.ts:590-599,956-969`
  removes the durable checkpoint before invalidating the in-memory destructive
  confirmation. A journal removal failure sets recovery blocked, so immediate
  submit fails closed, but it retains the token/current owner; later
  `recoverPending` at `640-674,721-730,972-993` can claim/adopt and re-authorize
  the cancelled token. **Change:** persist a cancellation tombstone or define an
  equivalent durable fail-closed state before/with local invalidation; merely
  clearing memory is insufficient. **Verify:** checkpoint removal failure first
  blocks submit, then `recoverPending` must not resurrect the cancelled token,
  and gateway mutation remains zero.

- **L21 — confirmed, MEDIUM.** `formalTaskControlLeaf.ts:537-549,603-667`
  accepts legacy `{ok:true,result}` for create/cancel/retry and performs target
  and durable mutation authority checks only when `mutation_processed` exists.
  **Change:** require the product mutation envelope for mutations; reserve
  legacy success for queries. **Verify:** every legacy mutation response rejects
  without replica or receipt change.

- **L22 — confirmed, LOW.** Frontend `createRouteDescriptor` repeats L10:
  `liveVoiceObservability.ts:688,900-928` accepts arbitrary contract-version
  text. **Change:** the same known/bounded stable-token rule must be shared on
  both sides. **Verify:** private markers, blanks and overlong values never reach
  the frontend sink.

- **L23 — fixed.** `LiveVoiceIntegratedRoutePanel.tsx:177,2094,2139-2143,
  2294-2297,2318,3597,4531,4889` caps pending owned progress at 128, fails
  closed and clears/rebinds it on session, effect and task transitions. Keep
  regressions for prolonged unavailable state, recovery binding and switching.

## 6. Revalidation of historical rejections C1–C13

- **C1 — rejection still valid.** `conversation_runtime_loop.py:1135-1150`
  intentionally lets critical control preempt normal work while preserving an
  earlier ACK/observation. This is the frozen lane policy; keep ordering and
  saturated-normal preemption tests.

- **C2 — rejection still valid.** Snapshot scanning exists at
  `conversation_runtime_loop.py:656-690`, but production admits one usable final
  text unit per response and response count is bounded. The alleged thousands
  of units per response are unreachable. Reassess only if streaming text units
  are introduced.

- **C3 — rejection partially overturned; alias of B42, no independent
  severity.** The
  effect half remains bounded by one final/response, but command IDs in
  `conversation_runtime_loop.py:179-192,766,772` can continue growing after
  product operation eviction. The exact repair and test are B42; do not create
  a second implementation issue.

- **C4 — rejection still valid.** The critical-token verb vocabulary at
  `critical_token_safety.py:424-433` is incomplete, but formal destructive P3
  confirmation is independently decided by parsed operation at
  `p3_authenticated_composition.py:2252-2332` and
  `formal_task_models.py:513-516`. This may justify classifier coverage work,
  not an authorization-bypass finding.

- **C5 — rejection overturned; confirmed MEDIUM.** `task_store.py:4290-4395`
  validates an outbox row but applies every returned observation; `_apply_observation`
  at `4738-4775` validates each observation internally, not against that outbox
  item. `ExecutorDeliveryResult` also binds only executor identity. A faulty
  executor can complete A's outbox with a valid B observation, mutate B and mark
  A delivered. **Change:** before any write, require every observation's
  task/attempt/executor ID/ref to equal item/spec/dispatch parameters.
  **Verify:** fake A delivery returning B observation yields
  `EXECUTOR_OBSERVATION_BINDING_MISMATCH` and zero change to A, B and outbox.

- **C6 — rejection still valid.** The unfiltered in-memory helper is used only
  by the fake vertical, whose caller accepts `task.create` and filters task
  events; the formal persistent core has a closed set. Require the formal filter
  before any new caller adopts the helper.

- **C7 — rejection still valid.** `executor_port.py:70-104` is a deterministic
  mechanism used by fake vertical/tests, not the formal cancel-policy owner.
  Keep controller-level cancel-before-start zero-execution coverage.

- **C8 — rejection still valid.** In `project_code_executor.py:3228-3276`,
  reserve return and `_applying.add()` have no await gap; close checks both
  in-memory/durable applying state and reports cleanup pending on timeout. The
  alleged late apply after successful close is excluded by current ordering.

- **C9 — rejection still valid.** Privacy `surface` is a closed classification
  label, while evaluator records carry arbitrary captured chunks which are all
  scanned. The original assertion that payload bytes cannot be submitted was a
  type misreading.

- **C10 — rejection still valid.** `agent_manager.py:841-862` pins exact
  acquisition ownership before await and exposes initialization error; the
  Project executor shields acquisition, saves release ownership and retains
  cleanup. Cancellation is neither swallowed nor reported as success.

- **C11 — rejection still valid.** `audioPort.ts` itself is unbounded, but the
  sole production route caps outstanding playout at 256 and ACK drains it. The
  claimed spread/RangeError scale is unreachable; keep peak-depth and ACK-drain
  tests.

- **C12 — rejection still valid.** The TS TurnCommitLedger remains unused in
  production; all instantiations are tests. It must be aligned with Python
  capacity/release before any production adoption, but is not a current runtime
  leak.

- **C13 — rejection still valid.** The current provider enforces 8 MiB total
  wire audio, about 174.8 seconds at 24 kHz s16, below the browser's 180-second
  / 9,000-frame bound. Keep a cross-sample-rate invariant test; reassess on a
  provider change.

## 7. Resolution of historical uncertainties D1–D3

- **D1 — confirmed, MEDIUM.** `conversation_runtime_loop.py:220-239` creates
  and awaits `_shutdown_future`; only normal drain at `1110-1118` settles it.
  `_run` finally at `1124-1133` fails lane futures but not shutdown, so worker
  cancellation/BaseException after close starts leaves close pending forever.
  **Change:** settle an unfinished shutdown future from finally with stable
  `RUNTIME_LOOP_CLOSED` failure and surface worker error. **Verify:** cancel the
  worker after creating a close waiter; close finishes with typed failure inside
  a bound.

- **D2 — confirmed, MEDIUM.** `_closing_interactions` is only `set[str]` at
  `agent_conversation_runtime.py:619`; close chooses the newest response but
  records only interaction ID, and any older response terminal at `2759-2791`
  closes it. **Change:** bind closing state to exact response/round generation.
  **Verify:** close generation 2, release generation 1 terminal first, remain
  CLOSING until generation 2 terminal.

- **D3 — confirmed, MEDIUM.** Cleanup loops in
  `interface_deep.py:9277-9294,9517-9536` and
  `jiuwenswarm_round_harness.py:841-896` repeat warning slices forever. Cancel
  ACK may be prompt, but authoritative cancel terminal, round settlement and
  teardown can hang indefinitely. **Change:** impose a total budget and transfer
  exact work to a process retained-cleanup owner; return pending/result-unknown,
  never false CLOSED, while retaining authority/no-history guards. **Verify:**
  never-ending interaction close gives prompt ACK, bounded caller completion,
  no fabricated terminal and visible retained cleanup.

## 8. Verification performed for this report

- Git baseline checks confirmed the isolated review branch and exact HEAD; it
  was 0 ahead / 0 behind local `hx/0812_live_voice_w3` and matched the remote-
  tracking ref at review start.
- A focused current-source Python command reused the existing local virtual
  environment and ran seven tests covering OpenAI active synthesis cancel,
  terminal/claimed cancel outbox behavior and registry origin eviction:
  **7 passed in 14.65s**.
- Those passing tests close A10 and corroborate adjacent lifecycle behavior;
  they do **not** close A2 or A13 because neither test suite exercises the
  queued-terminal cancellation race or abandoned accepted-origin sequence
  described above.
- A24, B31 and L23 were confirmed from current implementation plus committed
  regression source. Frontend scripts were not executed in the isolated
  worktree because ignored `node_modules`/cache dependencies are not present;
  no build result is claimed.
- This is a source/test review, not physical microphone, provider, network,
  browser-permission or controlled product-readiness evidence.

## 9. Implementation guidance and acceptance boundary

- Do not implement all 88 defects as one umbrella patch. Each coherent owner
  boundary needs intended behavior, risk tier, dependencies, exclusions and
  D-032 positive/negative/zero-effect evidence under `TESTING.md`.
- The first integration batch should cover A21/B41 privacy and C5/B9/B10
  authority fail-closed behavior. The second should freeze the common
  generation/replay-release pattern before addressing the many lifetime maps.
- Deduplicate implementation work: B17 is B13, and the surviving part of C3 is
  B42. Cross-layer pairs L10/L22 and contract-parity groups B29/L15–L17 should
  share fixtures rather than drift through parallel constants.
- A fix is not accepted merely because memory is capped. Evicted identity must
  remain unable to replay or revive authority, and cleanup timeout must not be
  reported as successful close.
- No code fix, `STATUS.md` transition, merge, remote update or push is included
  in this report.
