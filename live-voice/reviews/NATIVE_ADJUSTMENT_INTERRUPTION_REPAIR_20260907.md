# Native adjustment and interruption repair — 2026-09-07

Status: code repair verified; deployment pending. Tier 2, scoped repair authorized by “快速修复”.

Evidence: session `web_1a078b8778e_99c2b0c3c8cf`, retained report and
diagnostics under `logs/rehearsal-web_1a078b8778e_99c2b0c3c8cf/`.
The failed adjustment never entered the Task journal. Its original malformed
arguments were not logged, so the exact rejected field cannot be reconstructed.
The interruption did cancel a terminal delegate successor and raised
`RESPONSE_ALREADY_TERMINAL`, followed by media detach and two UI messages.

## Intended behavior and ownership

- Native business validation returns the rejected field and its constraint,
  without echoing private values. A corrective continuation repairs rejected
  arguments using existing schema and server facts; it must not repeat accepted
  operations, invent target/revision, or claim unexecuted changes succeeded.
- Native STOP cancels each running successor at most once; a terminal successor
  still permits the ordinary cursor-based playback stop. Check and cancellation
  are serialized in the Runtime loop. No Task cancellation is implied.
- Only the authoritative Native failed-turn notification inserts its chat
  message. Transport diagnostics remain visible without guessing a turn or
  competing with the exact failure. Distinct turns/activations remain distinct.

Owned surfaces: native_business_contract, openai_realtime_native_engine,
native_interaction_runtime, the Runtime loop's conditional cancellation helper,
LiveVoiceIntegratedRoutePanel, and their focused tests. Existing strict cancel
API, Cascade routing, business authority and action schema remain unchanged.

## Risks, dependencies and acceptance

Risks: duplicate mutations during correction, cancellation/completion races,
wrong-generation effects, lost playback truncation, hiding unrelated errors.
Dependencies: existing business-call ledger, observed context/revision checks,
Runtime serialization, Native turn/activation identity, actual audio ACK history.

Acceptance: field-specific rejection with zero admitted action; a corrected
task.adjust admitted once; replay/mixed-call/interrupted-turn behavior retained;
terminal and shared-successor STOP do not fail or duplicate cancellation and
preserve exact playback stop; no stale-response/Task/history side effects;
mounted UI merges fault layers and separates subsequent turns. Run affected
backend and frontend regressions, build, independent scoped review, then restart
the existing Demo with preserved provider/model/data and verify readiness.

Excluded: USER.md changes, VAD/latency tuning, model changes, task policy or
wire-schema redesign, old partial transcript persistence, new physical acceptance
claims. Physical microphone/demo acceptance remains open until exercised.

## Verification

- Reproduced terminal successor STOP raising `RESPONSE_ALREADY_TERMINAL` before
  the fix, and media-first mounted callback producing two failure messages.
- Backend: 272 passed across Native contract/engine/runtime, shared Runtime loop,
  business registry/authority/context, including real SQLite Task adjust/cancel.
- Mounted Native lifecycle: 21 passed, including media before any turn state,
  four fatal-event orderings, distinct subsequent failed turns, stale/replay,
  Task UI, model selection, text and work/Cascade isolation.
- Independent review found that merely sharing message IDs could guess an old
  turn and retain the generic first error in the insert-only chat store. Repaired
  by giving the authoritative failed-turn notification sole message ownership.
- Broader frontend regression: 644 passed, 24 failed, 1 skipped. All 24 failing
  names were rerun against the original `d5da166917` component bundle and failed
  identically by name (no newly introduced failing case). These pre-existing
  product-entry/Cascade fixture failures remain excluded, not reported as green.
  After review, reran all 21 affected Native mounted scenarios on the final code.
- TypeScript and production Live Voice build passed. Existing duplicate locale
  key and bundle-size warnings are unchanged and outside this repair.
- Independent read-only review `review_adjust_stop_repair`: no remaining blocker
  after the UI ownership correction. Main reviewed the complete scoped diff;
  `git diff --check` passed. Runtime data and USER.md unchanged by the repair.
- Evidence directory: `logs/native-adjust-stop-repair/`, including baseline
  comparison, backend regressions, mounted results and production build log.
- Deployment verification: pending, to be recorded in that evidence directory
  after a clean-source restart preserving model/provider/project/data/ports.
