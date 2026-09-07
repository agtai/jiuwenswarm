# Native startup defect exposed by candidate deployment

Main deployed the six-point candidate `3393ba8b` to the original clean w3 checkout.
The actual bundle, four ports, P2/P3 registration and real Speech probe passed;
the designated Chrome Session then failed to enter listening. This evidence keeps
the startup acceptance open even though the preceding scoped checks passed.

## Implementation checkpoint

This is a necessary Tier 3 lifecycle repair within the user's authorized local
startup verification. Preserve the six existing point commits and add one coherent
startup repair commit; do not rewrite them or change remote refs. Main owns the
frontend readiness boundary, docs, integration and actual deployment. A separate
worker owns registration/start-retirement lifecycle after its exact assignment;
independent review checks cancellation and late-return effects.

The browser's first attempt activated capture at 16:02:29.169 UTC and failed at
16:02:32.189 with `AUDIO_CAPTURE_MEDIA_ROUTE_NOT_ATTACHED`: 149 local frames,
zero sent/ACKed. The common three-second media attach budget also covers real
Native Provider bootstrap, despite its existing transport connect allowance of
five seconds plus session/context round trips. Later Provider startup success
survived browser retirement; subsequent same-activation attempts repeatedly hit
`MEDIA_NATIVE_SESSION_ALREADY_ACTIVE`. Main exited Live Voice and retained logs.
The exact readiness value and registry treatment will follow source/evidence
review, not merely repeated real-service retries.

Intended behavior: an initial Native media attach receives a reasonable finite
bootstrap allowance; Cascade, downlink readiness, first PCM/ACK and STOP deadlines
keep their own meanings. Cancellation/revocation fences the exact in-flight
startup. A late result may close its old Engine but must not register a live
session, start input/event/delivery/business-poll tasks, publish work or interfere
with a newer owner. No new protocol, model selection, automatic business replay,
project mutation or broader error classifier is included. Retained cleanup must
remain explicit and bounded if an external operation refuses cancellation.

Acceptance: delayed normal Native bootstrap succeeds; expired bootstrap fails
closed; Cascade retains its existing deadline; close/Session replacement during
pending startup produces zero successor-ineligible effects; stale completion
cannot resurrect an owner; cleanup unknown cannot be reported as complete.
Verify actual listening in the designated Chrome Session after independent
review, scoped checks and a controlled redeployment. Existing failed startup
evidence remains in Main's `logs/startup-browser-failure.json`,
`logs/startup-timeline.txt` and original `logs/swarm-20260907-180017.log`.

## Browser implementation and verification

Only initial Native attachment now has a 15-second readiness budget. Cascade
and downlink attachment retain three seconds; first-frame/ACK readiness retains
one second. This is a finite product startup bound, not a promise that every
Provider operation can finish within it. The existing 1,500-frame capture cap
and 800-frame Gateway input queue are unchanged. Waiting checks capture health
on each turn, so a muted/ended device or superseded owner fails promptly instead
of waiting for the larger deadline.

The full route run passed 155 tests after the deadline change. Final affected
checks passed 21 tests after the health check was added, including a successful
14,999-ms startup with 750 retained frames, 15,001-ms expiry, Cascade expiry,
close before attachment, the unchanged first ACK timeout and prompt device-mute
failure. Late attachment after failure/close sends no PCM and cannot report ready.
The mounted Native panel also passed a real four-second delayed attachment:
one activation, one socket, one readiness transition, no cleanup/retry loop and
no business request. The final complete mounted Native lifecycle group passed
all 26 cases. Strict scoped TypeScript checking passed. Independent Astra ultra
review passed the final frontend boundary, including the 14,999-ms positive case
and the health-check correction; this is not physical microphone/speaker evidence.

Evidence: `logs/startup-route-full.txt`,
`logs/startup-route-readiness-final.txt`, `logs/startup-mounted-delayed.txt`,
`logs/startup-mounted-native-final.txt`.
The first full run precedes the narrow health-check addition; it is not described
as a second full run of the final source. Final backend and independent-review
evidence is recorded in the [backend report](REALTIME_NATIVE_STARTUP_BACKEND_20260907.md).

## Backend and independent review

The backend retains one exact pending session before async bootstrap and releases
the global session lock while awaiting external work. Revocation synchronously
fences that owner and requests cancellation. Every bootstrap return rechecks the
original record object, subject, activation and expiry before publishing state.
Cleanup waits for startup and any shielded context read to actually settle before
closing the Engine. Unknown cleanup retains its exact owner and capacity; removing
the owner and releasing capacity are one atomic finalization.

The worker's complete registration file passed 179 checks, including 30 new startup
cases and the registered socket boundary. An in-memory counterfactual replacing
only `begin_native_interaction` with its deployed `3393ba8b` definition reproduced
the original late-return defect: one revived session, four consumers and zero
closes. The repaired function rejected the stale return, created no consumers and
closed once after startup settled. This isolates that function; it is not a second
complete deployment comparison.

Independent Astra ultra review passed both frozen boundaries. Its one reproduced
capacity-finalization cancellation finding was repaired and retested: owner and
capacity remain together on cancellation and are both removed on exact retry.
Original-record context fencing, three stages by seven retirement conditions,
unknown close outcomes, successor isolation and socket cancellation were reviewed.
No module finding remains. Main then integrated the return without changing the
five reviewed production/test blobs. The complete registration, Native downlink
source, Gateway media transport, dedicated media route and registered Web socket
files passed **358 checks in 12.64 seconds**:

```powershell
python -m pytest tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/gateway/test_native_response_downlink.py tests/unit_tests/gateway/test_browser_gateway_media_transport.py tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py tests/unit_tests/test_app_web_media_connect.py -q -o addopts='' --no-cov -o log_cli=false --tb=short
```

Main used the original checkout's `.venv/Scripts/python.exe`, integration-worktree
`PYTHONPATH`, and isolated `logs/startup-integration-data`. Output is retained in
`logs/startup-integration-backend-final.txt`. Changed Markdown links resolve and
scoped diff checks pass. Actual browser listening after clean-source redeployment
remains separate from this predeployment module evidence.
