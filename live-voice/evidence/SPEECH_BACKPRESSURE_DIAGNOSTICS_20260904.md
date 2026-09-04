# Speech backpressure diagnostics — 2026-09-04

## Accepted scope before implementation

User authorized passive diagnostics and necessary local redeployment, followed
by their own physical reproduction. Baseline: `77d6e67c98c7e14c85d01b5dce1558b299c28dc0`.
Owned boundary: Speech Recognition / Realtime Media observability, Tier 2
because instrumentation observes async sends, flow control and cancellation.

Owned surfaces: recognition socket observer, optional connection instrumentation
in the existing socket factory, recognition Adapter attachment, Gateway queue
timing, the bounded common diagnostic allowlist and their unit/integration tests.
Record write-buffer size/limits, actual pause/resume and drain wait, event-loop
heartbeat delay while sends are in flight, and oldest queued frame age plus
source sample progress. All records join existing media/capture/generation IDs.
Observers must not change wire bytes/order, locks, cancellation, deadlines,
queue sizes, fallback, routing or authority. Diagnostic failures drop evidence,
not audio; counters/timers are bounded and retired with their socket/send owner.
Connection peer locality and proxy policy are diagnostic hints, not proof that
the remote Provider consumed audio or that a particular intermediary is faulty.

Exclusions: fixing send/EOT locking, VAD/interruption policy, buffering or timeout
tuning, proxy/network changes, new provider traffic for diagnosis (apart from
the controlled launcher's required readiness probe), Agent/Tool/Task
behavior, frontend or protocol/schema changes, raw audio/text/headers/endpoints/
credentials, public deployment and remote updates. Keep VAD 800 ms and startup
lead 250 ms, current model configuration and existing project/data.

Acceptance uses root TESTING.md Tier 2 applicable dimensions: positive identical
wire output; slow flow-control vs scheduling signals; bounds/privacy; cancel,
failure and cleanup; concurrent send/stop and exact identity isolation; missing
instrumentation compatibility; actual loopback WebSocket transport plus affected
Speech/Gateway/lifecycle regressions. No persisted-format or feature-policy change.
Agent/Tool/Task/store authority is excluded and existing zero-effect regressions
must remain green. Independent review and deployment evidence are recorded only
after execution. Physical latency/root-cause closure remains pending the user run.

## Verification before deployment

Final affected run: **376 passed in 38.72 s**, using repository Python:

```text
-m pytest tests/unit_tests/live_voice/test_speech_socket_diagnostics.py
tests/unit_tests/live_voice/test_speech_precision_diagnostics.py
tests/unit_tests/gateway/test_audio_diagnostics.py
tests/unit_tests/live_voice/test_openai_streaming_speech.py
tests/unit_tests/live_voice/test_openai_realtime_session.py
tests/unit_tests/live_voice/test_batch_speech.py
tests/unit_tests/gateway/test_streaming_speech_route.py
tests/unit_tests/gateway/test_dedicated_media_registration.py
tests/unit_tests/live_voice/test_speech_lifecycle.py
tests/unit_tests/live_voice/test_generation_time_interruption.py
-q -o addopts='' -o log_cli=false --disable-warnings --tb=short
```

New diagnostic tests cover exact wire/no retries, slow drain and cancellation,
transport failure, throwing sink, unsupported transport, capture isolation,
keepalive exclusion, heartbeat lag/no catch-up bursts, timer retirement including
a diagnostic-only deadline for cancellation-hostile sends, queue bounds/cleanup,
privacy allowlists and unchanged legacy connection options. A real local WebSocket
round trip passes; a separate deliberate pause/resume on that connection proves
the library callbacks/drain integration, not actual network congestion. Existing
send/stop-lock race tests retain zero late append and zero business effects.
Ruff passes for both new Python modules; complete scoped diff review performed.

Independent `codex -c service_tier=fast review --uncommitted` exited 1. CLI 0.111.0
cannot use the configured current model and also reports incompatible local
state/model metadata. No CLI upgrade or global configuration changes attempted.
Manual complete-diff review is the recorded substitute, not independent review
credit; review closure and physical root-cause closure remain PARTIAL.

Timing interpretation: `socket_send_ms` excludes observer setup/finish work;
`drain_ms` may overlap event-loop delay and must not be added to it as separate
elapsed time. Buffer peaks are observed samples/callback maxima, not a kernel
high-water proof. `oldest_queue_age_ms` starts at this Gateway queue admission
(not browser capture); `frame_queue_wait_ms` belongs to the recorded last-dequeued
`frame_seq`. `pending_audio_ms` is queued 20 ms audio, excluding the in-flight
send. `sent_sample_end` remains the pre-existing attempted-send boundary, not
Provider receipt. Unsupported flow observation reports null drain duration.
Route hints and peer-loopback booleans do not disclose addresses or proxy secrets.

Pre-deployment read-only checks: same isolated default `deepseek-v4-flash`;
configuration SHA-256 `7017784bbf44dcf1fc1432fb91df05dc004f0dd1dd08b2dd1fb2628f68a22c57`;
two terminal Tasks and two terminal Attempts; retained business project clean,
with no remote. No user browser/microphone action or data cleanup performed.

### Post-commit timing-bound correction before user handoff

Initial implementation commit `5097ca71425ac3e0df6c0e46bf6391b011343d33` passed
the controlled deployment at 16:46, including full frontend build and real
TTS/STT plus rejection probes. During final review, a deterministic check found
that a send settling after the observer's own deadline incorrectly treated the
unobserved interval as loop lag. A new assertion failed first (90,900 ms reported
instead of the 900 ms actually observed). This same Tier 2 diagnostic-only scope
now freezes the observed lag peak on expiry and reports `observation_expired`
with null incomplete drain duration. It does not alter the send's deadline or
cancellation behavior. The same full affected command passes **376 tests in
31.65 s** after correction; new-module Ruff and complete changed-hunk review pass.
Replacement deployment follows before handoff; independent review remains
unavailable under the already recorded tool limitation.
