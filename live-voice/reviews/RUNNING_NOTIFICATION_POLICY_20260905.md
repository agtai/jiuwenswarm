# Running Task notification policy

## Accepted scope and ownership

The user requested suppressing unsolicited “Task is running” text and speech.
Keep Task/Attempt events and Registry status truthful and queryable. Preserve
terminal outcomes, blocked/decision-required notices and explicit operation
replies. Do not change Agent output, USER.md, cancellation/adjustment semantics,
audio ownership, schemas or durable ACK contracts.

Tier 2: the owned boundary is product notification eligibility and its unread
presentation selection. Task progress still projects accepted/running lifecycle
facts internally; a silent event must not allocate a product presentation,
history item or TTS request, and must not need a synthetic consumption ACK.
Later eligible notifications must pass the silent prefix, including reconnect.
Task Core, the progress Arbiter and query/UI state remain authoritative.

Verification owns the presentation-consumption and product Registry seams:
running silence in text/voice, live/offline terminal delivery, truthful result,
ACK/replay isolation and affected regression tests. Existing low-level tests
using running as a generic presentable example should use an eligible blocked
event; preserve their safety assertions. Physical microphone/speaker acceptance
and unrelated historical baseline failures are outside this module's claim.

The private demo entry and delay-material instructions are separately adjusted
to distinguish initial overview from complete-plan analysis. Input facts and
numbers remain unchanged; private backups stay outside Git.

## Verification

Source baseline: `a424f93957fc7aff0d3bbb7d40051671ddf9f4b2` plus this scoped
change. Product code changes only the shared eligible-event set and the three
Registry presentation/defer sinks; accepted/running projections remain intact.

All commands use a fresh ignored `JIUWENSWARM_DATA_DIR` and `--basetemp`, plus
`--no-cov --tb=short --log-cli-level=ERROR`. Controlled models are test doubles;
these checks do not establish model quality or physical audio acceptance.

- `pytest tests/unit_tests/live_voice/test_running_notification_policy.py
  tests/unit_tests/live_voice/test_task_presentation_consumption.py -q`:
  **25 passed**, exit 0. The eight new real-Store scenarios cover text/voice,
  active/offline completion/failure, no running presentation or Agent invocation,
  no synthetic ACK and exact class-isolated terminal consumption.
- `pytest tests/unit_tests/live_voice/test_product_composition_registry.py -q
  -k '(progress or notification or real_store_audio or real_store_text or runtime_ack
  or audio_ack_wins or later_audio_failure or audio_playout_failure or
  p2_close_settles_shared or terminal_after_voice_playout_failure or agent_ack_drains
  or foreground_ack_keeps) and not (unified_status_presents_authoritative or
  real_store_progress_replays_unread_predecessor or real_store_text_projects_recovery
  or real_store_audio_projects_recovery or voice_intent_create_uses_two)'`:
  **53 passed**, exit 0. Covers reconnect, failure fallback, deferred release,
  close/ACK races and all eight terminal-after-playout-failure timing cases.
- Full `test_task_progress_return.py`: **54 passed, 5 failed**, exit 1.
  A detached clean baseline worktree reproduces those same five failures:
  recovery boundary (text/voice), more-than-256 projection rollover and cancelled
  retry replay (text/voice). Their expected projection lists omit the already
  projected initial acceptance; product silence does not change that projection.
- The broader Registry runs also retain baseline failures in old deterministic
  status/retired P2-submit assumptions and retry/recovery notification-fact test
  readers. Baseline checks reproduce them, including voice retry. They are not
  passing evidence and are not fixed by this notification policy. The obsolete
  create-ACK notification scenario is replaced by a controlled foreground-ACK
  test against an already-running real Store Task, without claiming language or
  Task-creation coverage.
- Independent read-only review covered presentation eligibility, silent unread
  prefixes, deferred/fallback/reconnect paths, Task truth and ACK isolation. A
  test wording mismatch was corrected; no remaining product-code finding.

Private raw logs are retained under `logs/running-notification-*`; early runs
interrupted during coverage teardown are not counted as passing commands.
Controlled local deployment follows the existing runbook; its actual source and
probe results belong to the runtime manifest/log. Physical next-rehearsal
acceptance remains open.
