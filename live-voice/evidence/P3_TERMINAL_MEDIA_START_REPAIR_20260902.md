# Terminal Task AUDIO during media startup — 2026-09-02

Baseline: `0c6c1903323c82a4a6e032a4ef5d08ad845c1b75`.
Current judgement belongs to [STATUS](../STATUS.md); verification policy is root
[TESTING](../../TESTING.md). This record does not grant human acceptance.

## Intended behaviour and scope recorded before implementation

The exact retained terminal Task AUDIO must receive server-observed synthesis
authorization after the selected P1 media route is ready, including when the
notification arrives during startup of that same P1 object. P1 object identity
alone is not proof of an authorized underlying media generation. Preserve the
same notification request, response, unit and content; successful browser
playout precedes one AUDIO ACK. Failed reauthorization remains the existing
server-owned TEXT fallback. Exit, changed scope/owner and duplicate effect
continuations must produce no late audio, ACK, Task or Agent mutation.

Owned surfaces: Integrated Web captured-terminal arbitration and its existing
mounted regression cases. Tier 3 continuation of the notification repair because
this touches P1/P2/P3 presentation authorization and ACK ordering. No shared
schema, Gateway authorization rule, timeout, Provider configuration, task
operation, classification policy, remote ref or runtime deployment changes.

## Observed failed journey

The user tested the existing ordinary-Chrome session at 21:16:11 CEST. Local
runtime contract and served bundle identify the baseline above. Private log:
`logs/swarm-20260902-192503.log`; raw logs, credentials and databases are excluded.

- Task `task-2da087ec790e46e7b84475d17e6c641a` was created at 21:16:11.850,
  running at 21:16:12.344 and completed at 21:16:26.020. The canonical result
  includes `a.md`.
- Accepted/running AUDIO ACKs arrived at 21:16:27.838 and 21:16:32.408.
- Recognition reported Provider protocol degradation at 21:16:38.077 and
  timeout/batch fallback at 21:16:57.679–681.
- A notification pull and P2 media-authority refresh overlapped at
  21:16:58.600–678; the new capture first frame was accepted at 21:16:59.022.
- At 21:16:59.104 the browser reported `task_audio_playout_failed` for terminal
  response `response-task-progress-db87dc3b0eecfd6a71eff78a0ceaeeea67571216`,
  generation 4. No duplicate notification request (reauthorization replay)
  occurred in this interval.
- The durable voice cursor remains 3 (running), whereas TEXT reaches 5
  (terminal). This is a presentation failure, not unfinished background work.

## Cause and bounded correction

`0c6c19033` waits for owned recognition settlement and makes canonical TEXT
fallback visible. Its captured-terminal replay condition additionally requires
`capture_owner !== playoutOwner`. That misses an existing P1 object's new media
route: empty recognition can resume capture on the same object, with the old
route revoked before the new route is registered. A notification observed in
that gap cannot authorize synthesis on the later route.

The mounted regression holds `media.activate` after predecessor revocation,
delivers the exact terminal during that hold, then releases media startup. On
baseline product source this attempts synthesis without current media authority
and fails. The correction re-observes every retained terminal AUDIO after
capture arbitration, using the existing exact request/response/unit replay.
Concurrent effects still share one replay; the same owner/generation/Exit
fences and compare-and-clear guard remain in force. This adds at most one
ordinary replay for a stable retained-terminal owner, not another Task or Agent
submission and not a new notification pull identity.

The existing real Gateway/`FormalBatchSpeechService` test
`test_task_notification_reobservation_authorizes_late_media_owner` independently
establishes the authorization mechanism: notification before any media owner
causes `SPEECH_OPERATION_NOT_AUTHORIZED` with zero Provider calls; exact
re-observation after registration permits one synthesis. Its Provider is a
counting fixture, not a live acoustic boundary.

This defect matches the failed journey's notification/startup overlap and lack
of replay. The private log collapses the browser exception into
`task_audio_playout_failed`; it does not directly prove the precise client error
or empty-transcript outcome of that physical attempt. Treat that association as
the supported causal explanation, not a captured browser exception trace.

## Verification and scoped review

Tested product/test Git blobs, relative to the baseline above:

- `LiveVoiceIntegratedRoutePanel.tsx`: `11c7e51ef8d661e13d6f821c593b1d3ed4cf7f2b`.
- `liveVoiceIntegratedRoutePanelMounted.test.mjs`: `cb6e4c838157a01d8014825e77b4b4ddf9c0b4e0`.

Frontend commands, from `jiuwenswarm/channels/web/frontend`:

```text
node --test --test-reporter=spec --test-name-pattern="mounted captured terminal AUDIO" tests/liveVoiceIntegratedRoutePanelMounted.test.mjs
npm run test:live-voice-integrated-web
tsc --noEmit
vite build --mode live-voice --outDir node_modules/.cache/terminal-media-start-build-20260902
```

- RED: the new `natural_eot/play/media_start` case fails against baseline
  product source at the explicit unauthorized-terminal-synthesis assertion.
  The test recompiles its feature-enabled component from source; changing only
  the generic cached bundle is insufficient for this comparison.
- Final focused mounted checks: **10 passed**. This includes the seven existing
  recognition/recovery cases and three added startup cases: play, authorization
  failure, and Exit during authorization. Successful terminal audio has one
  synthesis, one replay, one history projection and one post-playout ACK, then
  resumes capture. Exit/failure has zero terminal synthesis/chat/ACK and zero
  extra Task mutation or Agent submission. Cleanup resources balance.
- Complete Integrated Web: **506 passed, 5 failed, 1 skipped (512 total)**.
  The same five failures are named in the
  [earlier repair record](P3_TERMINAL_NOTIFICATION_RECOGNITION_REPAIR_20260902.md).
  They remain unresolved; this is not a cumulative passing Gate.
- TypeScript and isolated production-mode Vite build: **PASS**. Existing i18n
  duplicate-key and import/chunk warnings remain. The served `dist` and runtime
  processes were not replaced.

Backend commands from repository root with the existing Python environment:

```text
python -m pytest tests/unit_tests/gateway/test_dedicated_media_registration.py -k "task_notification or non_task_audio_notification or mismatched_notification_batch or another_p2_activation" --no-cov -q
python -m pytest tests/unit_tests/live_voice/test_product_composition_registry.py -k "terminal_notification or audio_playout_failure or later_audio_failure or text_progress_web_ack" --no-cov -q
```

Gateway **18 passed / 48 deselected**; Registry **8 passed / 190 deselected**.
These exercise the actual authority resolver and canonical notification/ACK/
fallback boundaries, including exact scope and zero unauthorized Provider calls.

Applicable D-032 coverage: `P/S/T/C/R` includes terminal startup ordering,
same-object media recovery, long recognition, shared replay, completed playout
and resumed capture. `N/B/I/F` includes replay rejection, late Exit, wrong
subject/Session/connection/generation/response/unit/locale/rate, transfer limits
and expiry, invalid batches and truthful TEXT fallback. `K/X` is the affected
Integrated Web regression plus actual Gateway/Registry seams. No changed wire,
schema, persisted format, feature switch or Executor mutation requires a new
matrix path. Browser, microphone and live Provider acceptance remain unclaimed.

The complete scoped diff was cold-reviewed for retained delivery ownership,
request/response/unit identity, coalescing, post-await fences, playout-before-ACK
and zero extra mutations. The test fixture explicitly models predecessor
revocation rather than assuming every media rotation loses transferable
authority. No remaining introduced scope defect was found.

No callable independent local reviewer was available. Cold self-review is a
disclosed substitute, not independent Tier-3 review credit. Independent review,
the existing full-suite failures, controlled deployment and a fresh human
notification/recovery journey remain open. No remote ref or private runtime
configuration was changed; the earlier documentation stash remains separate.
