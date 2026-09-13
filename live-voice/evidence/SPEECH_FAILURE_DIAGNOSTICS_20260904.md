# Speech failure precision diagnostics — 2026-09-04

## Accepted scope before implementation

User authorized execution of the diagnostic/redeployment plan after Session
`web_1a06c30c782_96f1557633e5` failed. Baseline: `b13232cd3`.

Owned boundary: Speech Recognition / Observability, Tier 2 because observers
touch send-lock, receive, timeout and cancellation-sensitive paths. Move the
existing content-free bounded diagnostic sink to common ownership (mechanical
Tier 0 part), extend streaming Adapter and batch Adapter/service instrumentation
and their focused tests. No Gateway/browser wire contract changes.

Intended behavior: join existing capture/media/session and batch operation IDs;
separate send-lock wait, encoding and Socket send-await timing; log parsed
speech-stop arrival before lock wait and boundary publication after it; preserve
allowlisted protocol subcode, received event kind and scalar state; distinguish
batch HTTP connect/TLS/upload/response phases, HTTP timeout class and outer
operation deadline. Observers must be bounded, content-free and unable to change
fences, ordering, timeout budgets, cancellation or business effects. Socket send
completion is not Provider consumption; HTTP connect includes DNS and is not a
separate DNS measurement. Event-loop starvation cannot be ruled out by send-await
duration alone. No raw audio/text/wire events/headers/endpoints/exception strings.

Local deployment retains project/data, VAD 800 ms and startup lead 250 ms.
Inspect the currently effective private dialogue model configuration before
selecting the existing configuration directory; do not copy or overwrite keys.
Validate model configuration separately from Speech-only probes.

Exclusions: speculative root-cause fixes, new VAD/interruption policy, longer
timeouts, sentence TTS pipeline, UI seam/schema changes, new classifiers,
Agent/Tool/Task behavior or authority, public deployment and remote updates.
The misleading UI `activation` label remains a known separate presentation gap.

Acceptance: focused positive stream/final and batch success; protocol rejection
with safe subcode/state and zero business effects; locked send/stop ordering;
HTTP failure vs deadline/cancel; observer overload/failure privacy; affected
lifecycle/replay/isolation/flag-off regressions. No new feature flag or persisted
format; browser remains unchanged. Physical root-cause closure still requires
the user's two-turn microphone reproduction plus browser diagnostics/recording.

## Verification

Changed source: common diagnostic sink; streaming Speech Adapter; batch Speech
Adapter/service and its HTTP observer; two mechanical Gateway imports. Tests
own privacy/bounds, protocol subcodes, send/stop lock ordering, HTTP timeout
classes, deadline/cancel/replay and actual loopback HTTP transport callbacks.
Diagnostic labels have finite allowlists; unknown kinds/codes become `other`.
Routine send records sample every 50 frames; slow (>=100 ms) lock, encoding or
send observations and failures are also recorded. HTTP callback pairs are bounded
to one per phase/outcome. No timer, wire ordering or fence budget was changed.

Final affected command (repository `.venv/Scripts/python.exe`):

```text
-m pytest tests/unit_tests/live_voice/test_speech_precision_diagnostics.py
tests/unit_tests/gateway/test_audio_diagnostics.py
tests/unit_tests/live_voice/test_openai_streaming_speech.py
tests/unit_tests/live_voice/test_batch_speech.py
tests/unit_tests/gateway/test_streaming_speech_route.py
tests/unit_tests/gateway/test_dedicated_media_registration.py
tests/unit_tests/live_voice/test_speech_lifecycle.py
tests/unit_tests/live_voice/test_generation_time_interruption.py
-q -o addopts='' -o log_cli=false --disable-warnings --tb=short
```

The initial runs exposed two stale test imports after the mechanical sink move
and a direct private `_post` test caller missing diagnostic identity arguments;
updated these consumers without changing their oracles. New tests initially
missed the explicit test issuer reset fixture and supplied an already-consumed
MockTransport response; corrected the fixtures. Final rerun result recorded
below. These were implementation-time failures, not hidden baseline exclusions.

Complete scoped manual diff review covered content allowlists, finite queues,
failure/cancel propagation, unchanged authority/commit ordering, exact operation
joins and no duplicate append/receipt/Provider invocation. The local independent
`codex -c service_tier=fast review --uncommitted` attempt exited 1: CLI 0.111.0
cannot decode current model metadata and the selected model requires a newer
CLI. No independent review completed; no global CLI/configuration changes were
made. Tier 2 review closure therefore remains PARTIAL, not a candidate PASS.

## Private configuration and deployment

Existing server log `swarm-20260904-130715.log` retained. Browser export requested
before refresh; not yet received. No physical acceptance claimed.

Both the original user configuration and the current isolated configuration now
resolve to default `deepseek-v4-flash` / DeepSeek. Keep the isolated configuration
the user updated at 13:30, rather than overwrite it or copy keys. A private
pre-deployment check uses production `get_default_models` with that directory's
environment, rejects placeholders and performs an optional tool-free call via
the production model builder. It succeeded in 1,891 ms with no tool calls and no
Agent/Task dispatch. This validates configuration/Provider reachability, not the
complete conversational Agent path. Configuration SHA-256 before deployment:
`7017784bbf44dcf1fc1432fb91df05dc004f0dd1dd08b2dd1fb2628f68a22c57`.

Data stays in `live-voice-clean-runtime-20260904-093711`; business project remains
`live-voice-demo-20260904-093711` / `proj_ad135a77`. Read-only SQLite inspection
found two terminal Tasks and two terminal Attempts, no running work. Deployment
helper checks effective dialogue configuration before invoking the controlled
PowerShell 7 launcher; private helper/configuration/logs are excluded from Git.

Final affected rerun: **346 passed in 44.77 seconds**. `git diff --check` and
changed Markdown local-link checks passed. Frontend source was not changed;
deployment will rebuild the existing package. No microphone/speaker acceptance.

### Completed deployment at 13:58 (local UTC+02)

- Runtime source: `f66f89a85f180806d858f9734d02ca40956ad80d`, clean when launched.
  Controlled profile `formal-web-validation`, Cascade engine, branch
  `hx/0812_live_voice_w3`; no remote update.
- Preflight passed without stopping services. The first deployment's online
  `npm install` then stalled with an open HTTPS connection and no progress.
  Stopped only its verified PID 6640; launcher correctly returned failure.
  Retried with process-only `npm_config_offline=true`, `npm_config_audit=false`,
  `npm_config_fund=false`. Existing locked dependencies were up to date in 1 s;
  no lockfile/dependency change or global npm configuration write. This retry
  does not provide a fresh vulnerability audit or resolve earlier audit findings.
- Full `npm run build:live-voice` (TypeScript plus Vite) succeeded; Vite took
  56.21 s. Existing dynamic/static import and large-chunk warnings remain.
  `uv sync` resolved/checked existing dependencies without tracked changes.
- Runtime log: `logs/swarm-20260904-135751.log`; parent PID 18404;
  Agent 17292 on 18194; Web/Gateway 10140 on 19120/19121; UI 16336 on 6175.
  Startup log names `deepseek-v4-flash`, not `your-model-name`. Agent/Web process
  environments retain the same isolated config/data paths and VAD value 800.
  Configuration hash after deployment exactly matches the pre-deployment hash.
- The original acceptance URL returns HTTP 200. Served
  `/assets/index-DsZyj0lX.js` exactly matches the local build, contains startup
  lead `250` and `__liveVoiceDiagnostics`. Generation-time interruption flag
  remains false as before; no change to playback interruption behavior.
- Controlled probe passed real TTS→STT, receipt/claim, wrong-identity and forged
  claim rejection with zero business effects. New HTTP diagnostics emitted in
  this real probe: STT request-body send took **5485 ms**; subsequent response
  header wait took **671 ms**; body complete at about **6281 ms** from HTTP start.
  This is a batch HTTP upload observation, not the old streaming failure or a
  proof of network/OS/root cause. Connect/TLS/upload/response phases are now
  visible without content. The probe ran separately from the user's Session.
- Post-deployment SQLite still has exactly two terminal Tasks and two terminal
  Attempts. No browser refresh, microphone action, user Task creation or data
  cleanup was performed. Old log remains available; browser export is pending.

Next evidence: save the old browser snapshot before refreshing, then physically
repeat two speech turns and capture recording plus new Session URL and browser
snapshot. Compare media/capture identities, `adapter_stop_received` →
`adapter_stop_lock_acquired` → `adapter_stop_published`,
`adapter_receive_failed` subcode/state, and batch operation ID across HTTP
phase/failure/deadline. Existing browser heartbeat/playout/interruption records
remain necessary for endpoint and ineffective barge-in diagnosis. Neither
diagnostics nor one successful probe establishes VAD/physical acceptance.
