# P2 Notification Bounded Pull Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace one-RPC-per-observer-notification P2 delivery with a bounded
batch of at most 16 while preserving exact final/error/Task/ACK authority.

**Architecture:** The server long-polls for one notification, drains only
already-queued notifications, and stops the batch at the first authoritative
barrier. The Web owner retains the public `nextNotification()` API, queues a
validated batch locally and returns one item at a time. Independent server and
Web flags preserve the exact legacy route when disabled.

**Tech Stack:** Python asyncio/pytest, TypeScript, Node tests, existing P2
activation/notification protocol and causal benchmark.

**Spec:**
[LATENCY_OPTIMIZATION_PLAN_2026-08-18.md](LATENCY_OPTIMIZATION_PLAN_2026-08-18.md)
§§3.3, 4 and 7.

## Global Constraints

- Capability/module: P2 notification transport; D-046 Tier 3 shared protocol.
- Base: current reviewed branch after causal A1; no rebase onto Hongxing.
- Batch maximum: 16; request accepts only canonical integer `2..16`.
- Legacy request/response remains byte-shape compatible when either product
  build uses batch size 1 or the server flag is off.
- Only pure observer `agent_event` notifications without presentation,
  progress, source event or error may precede another item in the same batch.
  The first final/error/Task/progress/PresentationUnit is included as the last
  item and stops draining.
- Draining never waits after the first notification and never crosses a stale,
  detached, closed or superseded notification lease.
- One batch request owns one request ID and one notification operation
  sequence; identical retry returns the identical retained batch without a
  second dequeue.
- Browser public API remains `nextNotification(): Promise<JsonObject>`.
- Close discards any unconsumed local observer queue; no queued item can revive
  an old activation generation.
- Feature flags:
  `JIUWENSWARM_LIVE_VOICE_P2_NOTIFICATION_BATCH_ENABLED=1` and
  `VITE_FEATURE_LIVE_VOICE_P2_NOTIFICATION_BATCH=true`.
- No change to Agent generation, notification production, Tool/Task/history,
  Presentation ACK, audio, STT, TTS or Browser playout.

## Task 1: Freeze a candidate-neutral benchmark input

**Files:**

- Modify:
  `jiuwenswarm/channels/web/frontend/scripts/liveVoiceP2NotificationCausalBenchmark.mjs`
- Modify:
  `jiuwenswarm/channels/web/frontend/tests/liveVoiceP2NotificationCausalBenchmark.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Contract:** Add required CLI `--batch-size 16`, pass
`notification_batch_size: 16` into the production owner, and make the fake
transport understand both legacy `notification` and future
`notification_batch` responses. The current owner ignores the prospective
constructor field and therefore must retain 50/250/500 RPCs.

- [x] Write a failing test requiring `notification_batch_size: 16` to be passed
  while the current owner still produces the legacy A1 curve.
- [x] Run the focused test and observe RED on the missing argument/report field.
- [x] Implement the minimal candidate-neutral fake transport and closed report
  field `batch_size`.
- [x] Run focused tests, integrated Web and formatting checks.
- [x] Commit as `test(live-voice): freeze bounded-pull benchmark input`.
- [x] Execute replacement A1 in a clean detached worktree: five samples each,
  85 ms delay, batch size 16. Mark the earlier `a9142dd2d` A1 preliminary and
  record the new exact reference commit/result.

**Pre-correction A1:** `PASS — P2 CAUSAL BASELINE ONLY`

- Exact reference: `c8f24834bb92205c6a23a85035066ea8f0b3e8cc`
- Run ID: `p2-a1-batch16-20260820T233928Z-c8f24834b`
- Five attempts per population; batch-size input 16; owner remained legacy
- RPC totals: 50 / 250 / 500
- p50: 863.272 / 4,330.481 / 8,649.853 ms
- p95: 869.882 / 4,365.143 / 8,700.057 ms
- All forbidden effects: zero

The GREEN B run exposed that this otherwise valid legacy measurement used a
runner completion oracle tied to delivered item count. That is equivalent for
the one-item legacy owner but cannot execute a batch candidate. Commit
`31f9209d66682d19745acd1d2c15a16b59fc75e2` repairs only that candidate-neutral
oracle; it is now the exact A1/A2 reference.

**Corrected-harness A1:** `PASS — P2 CAUSAL BASELINE ONLY`

- Exact reference: `31f9209d66682d19745acd1d2c15a16b59fc75e2`
- Run ID: `p2-a1-r-batch16-20260821T001711Z-31f9209d6`
- Five attempts per population; batch-size input 16; owner remained legacy
- RPC totals: 50 / 250 / 500
- p50: 864.293 / 4,348.227 / 8,658.478 ms
- p95: 873.600 / 4,351.440 / 8,700.760 ms
- All forbidden effects: zero

## Task 2: Bounded runtime drain

**Files:**

- Modify: `jiuwenswarm/server/live_voice/agent_conversation_runtime.py`
- Modify: `jiuwenswarm/server/live_voice/product_p2_interaction_adapter.py`
- Modify: `tests/unit_tests/live_voice/test_agent_conversation_runtime.py`
- Modify: `tests/unit_tests/live_voice/test_product_p2_interaction_adapter.py`

**Interfaces:**

- `_BoundedNotificationBuffer.get_nowait(...) -> AgentConversationNotification | None`
- `AgentConversationRuntime.drain_notifications_for(lease, *, limit) -> tuple[AgentConversationNotification, ...]`
- `P2ActivationLease.next_notifications(binding, *, limit) -> tuple[AgentConversationNotification, ...]`

- [x] RED: exact lease drains queued notifications in publish order, returns
  immediately below the limit, and rejects `0`, `17`, bool, detached, stale and
  foreign leases with zero consumption.
- [x] GREEN: add only the nonblocking drain methods; retain the existing
  `next_notification*` behavior unchanged.
- [x] Verify close/detach races cannot consume after the lease fence.
- [x] Run the two focused Python suites, Ruff, py_compile and diff check.

## Task 3: Server batch protocol and replay

**Files:**

- Modify: `jiuwenswarm/server/live_voice/product_composition_registry.py`
- Modify: `tests/unit_tests/live_voice/test_product_composition_registry.py`

**Wire shape when enabled:**

```json
{
  "status": "notification_batch",
  "notifications": [
    {
      "status": "notification",
      "session_id": "exact",
      "correlation_id": "exact",
      "interaction_id": "exact",
      "activation_id": "exact",
      "activation_generation": 1,
      "kind": "agent.output",
      "publish_seq": 0
    }
  ],
  "session_id": "exact",
  "correlation_id": "exact",
  "interaction_id": "exact",
  "activation_id": "exact",
  "activation_generation": 1
}
```

- [x] RED: flag-off rejects `max_notifications` before dequeue; legacy request
  remains exact. Flag-on returns up to the requested limit, includes full bound
  items, stops after the first authoritative barrier and never waits to fill.
- [x] RED: same request ID replays identical bytes; changed limit conflicts;
  wrong sequence/generation/scope, concurrent predecessor and invalid bounds
  consume zero notifications.
- [x] GREEN: add the setting/env flag, closed parameter parser, barrier-aware
  drain and retained batch response.
- [x] Run the complete registry suite, related P2 adapter/runtime suites, Ruff,
  py_compile and diff check.

## Task 4: Web owner queue and feature flag

**Files:**

- Modify:
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts`
- Modify:
  `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`
- Modify: `jiuwenswarm/channels/web/frontend/src/featureFlags.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/vite-env.d.ts`
- Modify:
  `jiuwenswarm/channels/web/frontend/tests/productWebActivation.test.mjs`
- Modify:
  `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs`

**Interfaces:** Constructor accepts `notification_batch_size?: number`; default
is 1. `nextNotification()` returns queued items without another RPC, but one
in-flight call still coalesces to one first result.

- [x] RED: batch 16 turns 10/50/100 items into 1/4/7 RPCs, preserves ordered
  item delivery and stops each server batch at an authoritative barrier.
- [x] RED: empty, oversized, open, foreign, duplicated or decreasing batch
  items fail closed; response loss retries the same request; close/stale
  generation clears the local queue.
- [x] RED: flag-off Panel constructors omit batch size; flag-on recovery,
  initial and successor owners all pass exactly 16.
- [x] GREEN: implement the bounded local queue/parser and pass the flag at all
  three owner construction seams.
- [x] Run focused owner/Panel tests, full integrated Web, frontend build,
  Prettier and diff check.

**Implementation checkpoint (2026-08-21):** Tasks 2–4 are GREEN in the B
worktree. The complete affected Python set passed 255/255; Integrated Web
passed 421/421; the production frontend build completed with 4,645 modules.
Ruff, `py_compile`, scoped Prettier and `git diff --check` passed. The frozen
runner exposed one candidate-neutral defect during the first B rerun: it tied
`notification_sequence` and its completion oracle to delivered item count
instead of transport-RPC count. The correction leaves legacy A1 timings and
effects unchanged, permits the contracted per-RPC sequence under batching, and
derives expected serial wait from observed RPC count. It is part of the
reviewed benchmark harness, not product optimization credit.

The independent Tier-3 review then returned `READY` after one Important
finding was reproduced and fixed in RED/GREEN: a nested
`agent_event.error_reason` is now an authoritative barrier on the server and
cannot precede a Web batch tail. No Critical, Important or Minor finding
remains. This grants code-review readiness only; performance still depends on
B and unchanged-source A2 below.

## Task 5: Candidate B and unchanged A2

- [x] Complete scoped self-review and one independent Tier-3 module-boundary
  review; remediate all Critical/Important findings.
- [x] Commit B in its separate worktree with one coherent message.
- [x] Run B using the frozen benchmark: five samples, 85 ms, batch size 16.
  Expected notification RPC totals are 5, 20 and 35 for 10/50/100.
- [x] Rerun unchanged reference A2 at the exact replacement-A1 commit.
- [x] Compare B against both A1 and A2. Accept only if latency and RPC count
  improve against both while baselines remain stable and all forbidden effects
  remain zero.
- [x] Record sanitized A1/B/A2 results in this plan and STATUS. Keep raw JSON
  outside Git.
- [x] Defer physical Browser confirmation until after the causal decision.

**A1/B/A2 decision:** `ACCEPT — P2 CAUSAL COMPONENT EVIDENCE ONLY`

- R/A1/A2 commit: `31f9209d66682d19745acd1d2c15a16b59fc75e2`
- B commit: `c1b4a47f51b0b200b12e2e544617577d7f307c69`
- A1 run: `p2-a1-r-batch16-20260821T001711Z-31f9209d6`
- B run: `p2-b-batch16-20260821T002105Z-c1b4a47f5`
- A2 run: `p2-a2-r-batch16-20260821T002121Z-31f9209d6`
- Five attempts per population; 85 ms controlled RPC delay; batch input 16
- All Agent, Tool, Task, history, audio and product mutation effects: zero

| Notifications | A1 RPC / p50 / p95 | B RPC / p50 / p95 | A2 RPC / p50 / p95 | B p50 gain vs A1 / A2 |
|---:|---:|---:|---:|---:|
| 10 | 50 / 864.293 / 873.600 ms | 5 / 85.823 / 91.008 ms | 50 / 860.659 / 867.540 ms | 90.070% / 90.028% |
| 50 | 250 / 4,348.227 / 4,351.440 ms | 20 / 343.704 / 349.175 ms | 250 / 4,305.376 / 4,343.331 ms | 92.096% / 92.017% |
| 100 | 500 / 8,658.478 / 8,700.760 ms | 35 / 615.209 / 617.248 ms | 500 / 8,643.205 / 8,681.116 ms | 92.895% / 92.882% |

A1 and A2 remained stable while B reached the exact expected 5/20/35 RPC
totals. B therefore receives causal P2 component credit and is retained for a
later physical Browser confirmation. These numbers do not measure capture,
STT, Agent/model execution, TTS, WebAudio, first audible or complete Live Voice
latency. Raw mode-600 JSON reports remain outside Git.

## Completion Gate

- Feature-off production behavior and wire shape are unchanged.
- Feature-on batch size is bounded at 16 and stops at the first authoritative
  barrier.
- Final/error/Task/presentation order, replay, generation and ACK ownership pass
  the complete applicable P/N/B/S/T/C/R/I/F/K/X matrix.
- B beats both unchanged baselines with the frozen runner.
- No E2E or physical latency credit is claimed.
