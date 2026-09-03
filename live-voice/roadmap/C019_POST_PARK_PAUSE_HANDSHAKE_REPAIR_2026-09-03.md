# C019 post-PARK ordinary pause handshake repair — child packet

- **Date:** 2026-09-03
- **Capability:** Speech Synthesis / Realtime Media (Gateway streaming-TTS route)
- **Tier:** 2 — concurrency/state child inside the already integrated C019
  bounded-pause and parked-successor boundaries. No new contract.
- **Base:** `f13abf57212ce40d0f67dd1ad521c005ab0febb2`
- **Owned files (sole writer lease):**
  - `jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py`
  - `tests/unit_tests/gateway/test_streaming_synthesis_route.py`
  - this document
- **Dependencies:** the bounded Provider-pause source introduced by
  `944959e1d`/`d2e2a2a96` and retained in this rebaseline
  (`_pause_wait_seconds`, product 55 s inside the Provider's 60 s
  `MAX_SYNTHESIS_PAUSE_SECONDS`); the C019 PARK/PROMOTE lifecycle; the physical
  pilot evidence in
  `live-voice/evidence/C019_TASK1_ABA_PHYSICAL_PILOT_20260903.md`.

## Problem

Physical B/long (`response-unified-f4a8602654e0113fbdb2c30c4a7f2ea7`, pilot root
`c019-task1-aba-20260903T114834Z`): unit 4 was parked 65.1 s, promoted cleanly,
and its Gateway queue reached 8/8. The route bounded the ordinary
`handle.provider.pause_synthesis(handle.ref)` handshake by `_queue_wait_seconds`
(product default 2 s). The Adapter acknowledges an ordinary pause only at a
reader boundary, and after the long PARK the Provider's next event arrived
≈ 2.7 s after the pause request, so the handshake deadline expired
(`resume_requested` at +2.003 s) and the route failed closed although first
audio had already been emitted. Four of five units completed.

Two further defects were uncovered while proving the repair:

1. The route's `except TimeoutError` handler in `_enqueue_frame` read
   `queued_at`, which was only bound *after* the pause handshake. A handshake
   deadline therefore raised `UnboundLocalError` inside the handler, skipped the
   `queue_pressure` diagnostic and the `QUEUE_EXHAUSTED` classification, and
   `_reason_for_exception` defaulted the outcome to
   `STREAMING_SPEECH_PROVIDER_UNAVAILABLE` — the exact reason the physical log
   recorded. Probe evidence (test harness, pre-fix):
   `('UnboundLocalError', reason=None, "cannot access local variable 'queued_at'…", __context__=TimeoutError)`.
2. Independent review (C0/I1/M1) of the first GREEN: moving the handshake onto
   `_pause_wait_seconds` let one ordinary pause spend a **fresh** pause budget
   on the handshake and another on the blocked queue admission, and
   `_wait_for_resume_watermark` renewed its wait per iteration. A reviewer
   probe measured ≈ 0.19 s for a configured 0.10 s budget; in production the
   summed ownership could exceed the Adapter's 60 s hard pause lifetime and
   erase the intended five-second margin.

## Intended behavior

- One **absolute ordinary-pause deadline** is created when the full-queue
  ordinary pause takes ownership (`flow_state → ORDINARY_PAUSING`). The Provider
  pause handshake, the blocked queue admission and the subsequent
  resume-watermark ownership draw only on its remaining positive budget; no
  phase renews it.
- An ordinary Provider pause ACK that arrives after `queue_wait_seconds` but
  before the deadline remains valid; the exact stream resumes and drains in
  order with zero cancellation.
- A pause that never acknowledges, or a late-but-valid ACK followed by a queue
  admission that never gets downstream progress, fails closed **by the original
  deadline** — not by a sum of budgets — classified truthfully as
  `STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED` (`text_or_retry`, visible,
  `first_audio_emitted=True`, not batch-eligible), with exactly one cleanup
  resume and exactly one Provider cancel; a late Provider event cannot revive
  the fenced stream.
- Cleanup resume is bounded by the smaller of its existing queue-wait bound and
  the remaining ordinary-pause budget while that budget is positive. Once the
  budget has expired (the failure path), cleanup resume keeps its queue-wait
  bound so the single cleanup resume still reaches the Provider; process-control
  and cancellation behavior are unchanged.
- PARK/PROMOTE leases (`park_deadline`, `prefetch_decision_deadline`, the
  promoted put) and drain-only admission retain their distinct existing
  deadlines. The put issued after PROMOTE keeps the undiminished ordinary put
  bound via `promoted_put_timeout_seconds`.
- Reader-boundary ACK semantics are preserved: the Adapter is **not** changed
  to acknowledge while an SSE read is in flight.

## Change

`streaming_synthesis_route.py`:

- `_enqueue_frame`: `pressure_started_at`, `pressure_deadline` (set to
  `now + _pause_wait_seconds` at ordinary-pause ownership) and a content-free
  `pressure_phase`. Handshake uses `_remaining_pressure_budget(deadline)`;
  admission uses the remainder when paused (drain-only keeps
  `_pause_wait_seconds`, unpaused keeps `_queue_wait_seconds`); the watermark
  wait receives the deadline; cleanup resume applies the `min(queue_wait,
  remaining)` rule above.
- `_wait_for_resume_watermark(handle, *, deadline=None, started_at=None)`:
  with a deadline each iteration waits only the remaining budget and fails
  `QUEUE_EXHAUSTED` when it is gone; without one, behavior is unchanged.
- `_queue_put_with_optional_prefetch(..., promoted_put_timeout_seconds=None)`:
  the post-PROMOTE put is bounded independently of the diminished ordinary
  budget.
- Module helpers `_remaining_pressure_budget` (raises `TimeoutError` on an
  exhausted budget so the existing handler classifies it) and
  `_log_queue_pressure(handle, phase, started_at)` emitting the existing
  `live_voice_streaming_synthesis_queue_pressure` diagnostic with
  `source_state` ∈ {`pause_handshake_timeout`, `queue_put_timeout`,
  `resume_watermark_timeout`} and `wait_elapsed_ms` measured from ownership
  start. No public reason or schema is added.

Diff: route `+151/−29`; tests `+296/−1` (`pause_gate` on `_FakeProvider`, one
shared post-promotion helper, three tests, one retuned scaled parameter).

## Explicit exclusions

No change to: Adapter code, Provider implementation, constants, queue capacity
or chunk count, PARK/PROMOTE semantics, Media/P2/Presentation ACK, Browser
code, public schema, Provider capability, reason enums, or the integrated
bounded-pause semantics.

## TDD record

### RED 1 (against `f13abf572`)

```
uv run --locked pytest -q --no-cov -p no:cacheprovider \
  "tests/unit_tests/gateway/test_streaming_synthesis_route.py::test_post_promotion_pause_ack_after_queue_wait_within_pause_wait_drains" \
  "tests/unit_tests/gateway/test_streaming_synthesis_route.py::test_post_promotion_pause_without_ack_fails_closed_by_pause_wait"
```

- `…_drains` **FAILED**: `assert pull.outcome.completed is True` → outcome
  `completed=False, first_audio_emitted=True, batch_eligible=False,
  reason=PROVIDER_UNAVAILABLE, fallback_action=TEXT_OR_RETRY` — failed at the
  0.01 s queue-wait bound while the ACK was released at ≈ 0.03 s.
- `…_fails_closed_by_pause_wait` **FAILED**:
  `assert 0.1 <= 0.015435708999575581`; after the budget change alone it failed
  on `assert PROVIDER_UNAVAILABLE is QUEUE_EXHAUSTED` (the `queued_at` defect).
- `2 failed in 2.46s`.

### RED 2 (against the first GREEN, review fix)

```
uv run --locked pytest -q --no-cov -p no:cacheprovider \
  "tests/unit_tests/gateway/test_streaming_synthesis_route.py::test_post_promotion_late_pause_ack_with_stalled_queue_fails_by_single_pause_wait"
```

- **FAILED**: `assert 0.17339779200119665 < (0.1 * 1.4)` — late ACK at
  0.06 s plus a fresh 0.10 s admission budget; total ownership ≈ 1.7× the
  configured deadline.

### GREEN

Focused three tests → `3 passed in 2.25s`.

One pre-existing scaled parameter was retuned:
`test_slow_consumer_makes_bounded_backpressure_progress[8-30-0.02-0.05-6]` →
`pause_wait 0.05 → 0.3`. Its 20 ms consumer needs five pulls (≈ 100 ms) to
reach the low watermark, which cannot fit a single 50 ms ownership budget and,
under the Adapter's absolute pause lifetime, must not. The asserted behavior
(ordered completion, `pause_count == resume_count`, `pause_count ≤ 6` for 30
frames) is unchanged.

## Automated acceptance

| Check | Result |
|---|---|
| Focused three tests | `3 passed` |
| `tests/unit_tests/gateway/test_streaming_synthesis_route.py` | `82 passed in 13.08s` |
| `test_product_streaming_synthesis.py` + `test_dedicated_media_registration.py` + `test_openai_streaming_speech.py` | `190 passed in 6.43s` |
| `ruff check` (two Python files) | All checks passed |
| `ruff format --check` (two Python files) | already formatted |
| `git diff --check` | clean |

Existing coverage retained without duplication:
`test_declared_provider_pause_timeout_fails_closed_and_resumes_once`,
`test_promoted_prefetch_resumes_later_ordinary_queue_pressure`,
`test_park_suspends_inflight_gateway_provider_event_deadline`,
`test_cancel_during_watermark_wait_never_resumes_fenced_provider`, and the
cancel/late-audio fencing tests.

## Physical gate

Tests grant **no** physical or latency credit. The real B/long journey on the
exact clean candidate remains mandatory: the Provider stall after a ≥ 60 s PARK
is inferred from one sample and is not reproduced by these tests. The physical
defect is not claimed fixed.

### Physical follow-up

Two later clean B/long attempts produced one failure and one PASS. The first
failed after a successful unit-3 promotion with
`STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED`; the second completed 5/5 units with
zero Browser-record loss and no operator-observed audible gap. The second
source differed only by rendering the already recorded queue-pressure phase in
the ordinary log message, so it cannot establish that this repair caused the
success. Physical stability and the exact intermittent timeout phase remain
open. See
[`C019_B_LONG_RECOVERY_SMOKE_20260903.md`](../evidence/C019_B_LONG_RECOVERY_SMOKE_20260903.md).

## Residual concerns

- `_reason_for_exception` still defaults any non-route, non-speech exception to
  `PROVIDER_UNAVAILABLE`; the `queued_at` defect shows how quietly that default
  can mask a Gateway-side cause. Out of scope for this child.
