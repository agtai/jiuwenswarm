# R2 generation, delivery and playback lifecycle

The accepted [repair packet](REALTIME_ACCEPTANCE_REPAIRS_20260907.md) assigns this
Tier 3 seam to the lifecycle worker. Baseline: `af6a5bbb0cadd0e260e12961ee33f737db489d31`.

Generation completion, delivery retirement and actual rendered playback are
separate facts. A terminal response with retained PCM keeps its media ownership
until the exact browser rendered acknowledgement or explicit STOP. Source close
and transport acknowledgement never release playback ownership. Finite incomplete
generation can acknowledge actual playback without claiming successful generation
or publishing complete heard history.
Provider control and response admission must not wait behind media delivery.
Transport failures retain only bounded exception classification and close codes,
never exception messages, endpoint data, credentials or wire content.

Owned surfaces: Native Engine, Gateway event/delivery seam, Realtime session
diagnostics and affected tests. Dependencies: existing Runtime admission and exact
media closure. Exclusions: R1 output budget, R3 browser fault-tail policy, R4 UI,
real services, private configuration and physical acceptance. Main performs the
independent integrated review; this worker records cold diff review and focused
verification below.

Acceptance covers successful, incomplete, failed and cancelled generation with
stalled media; exact delivery retirement versus played ACK; successor/STOP order;
stale/wrong-scope settlement; bounds and cleanup; and content-free exception
diagnostics. No path may create unadmitted PCM, Agent/Tool/Task execution, heard
history or fabricated completion.

## Verification

The focused continuation/session/diagnostics/Gateway batch exercised 273 cases;
272 passed and the old saturation-barrier assertion failed. The Engine/Runtime
batch exercised 194 cases; six tests encoded the former impossible-partial-ACK
assumption. Those assertions now require finite delivery plus real playback ACK,
or exact STOP. Final affected reruns passed: Gateway 142 and Engine 162. The
unchanged continuation/session/diagnostics 131 and Runtime 32 cases passed in
their initial runs. No provider or service was contacted.

Commands use the original repository `.venv/Scripts/python.exe`, this worktree
as `PYTHONPATH`, and a private `.repair-test-data` data directory. Targets are
`test_native_continuation_preparation.py`, `test_native_transport_diagnostics.py`,
`test_openai_realtime_session.py`, `test_dedicated_media_registration.py`,
`test_openai_realtime_native_engine.py`, and `test_native_interaction_runtime.py`.
Final reruns use `--no-cov -o addopts='' -o log_cli=false --show-capture=no
--tb=short`; the repository default broad coverage report is unnecessary here.

Cold diff review checked that delivery settlement never advances preparation,
incomplete generation remains non-presentable, old/wrong response receipts cannot
advance the successor, STOP still fences remaining output, control bypass does
not deliver the queued terminal after source saturation, and diagnostics contain
only fixed exception kinds/numeric socket facts. The tests cover completed,
incomplete, failed and cancelled terminal PCM with transport finished but actual
rendering stalled. Main's independent review and physical acceptance remain open.

Main's first independent review found that the production diagnostics allowlist
would strip the new transport fields. Classification now uses the existing
`error_type` token and explicitly permits the three numeric socket facts; a real
queue/sink JSON test verifies retention and secret exclusion.

The review also identified a silent-predecessor ordering race. A held Runtime
terminal plus ready work reproduced a second `response.create` before terminal
delivery (2/2 failing cases before the fix). Generation with no emitted frames
now waits for exact delivery acknowledgement; this wakes scheduling without
claiming playback. Provider control remains live during a held Runtime terminal
RPC, and rejected terminals fence the response without releasing successors.
Unemitted sub-frame PCM discarded on failure follows this silent path. Audio
ownership uses emitted frame sequence, avoiding an impossible ACK for bytes that
never left the Engine. Engine unit fixtures explicitly model immediate acceptance
of silent terminals; race cases disable that consumer and control its ACK.

Review repair checks: 279 passed in the combined Engine/continuation/transport/
diagnostics batch, with one pre-existing diagnostics test capturing older queued
records; it now flushes the queue before installing its sink. The final targeted
49 tests passed, including real diagnostic sink, silent/partial terminal cases,
held Runtime acceptance/rejection, finite EOF and wrong-scope controls. No provider
calls, real sessions or services were used.

Main's independent review is closed after those two repairs. The cumulative
R1–R6 Native/Gateway run passed 757 checks, including the final R3 typed-fault
bridge and R6 persistent control reader (`logs/integration-backend-final.txt`).
Physical playback remains a separate user-acceptance boundary.
